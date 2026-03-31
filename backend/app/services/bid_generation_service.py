"""
投标章节 AI 生成服务 — RAG + LLM 驱动的投标文件章节生成

流程:
  1. 加载企业信息 + 招标要求 + 章节模板
  2. RAG 检索: StdClause(法规) + ChapterSnippet(模板) + BidCase(历史案例)
  3. 加载可用图片资源
  4. 调用 LLM bid_generation prompt 生成章节内容
  5. 保存到 BidChapter

架构红线:
  - 报价数值禁止用 LLM 输出，必须从 QuotationSheet 计算引擎注入
  - 所有向量检索必须注入 tenant_id 隔离
"""
import asyncio
import json
import os
from typing import AsyncGenerator, Optional

import yaml
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.prompt_manager import prompt_manager
from app.core.llm_selector import LLMSelector
from app.models.bid_project import BidProject, BidChapter, BidProjectStatus
from app.models.enterprise import Enterprise
from app.models.image_asset import ImageAsset
from app.services.bid_chapter_engine import (
    get_chapter_templates,
    map_requirements_to_chapters,
    build_chapter_outline,
)
from app.services.bid_project_service import BidProjectService


def _build_enterprise_info(enterprise: Enterprise, credentials: list = None) -> str:
    """构建企业信息文本块（含资质编号，防止 LLM 编造）"""
    lines = [f"企业名称：{enterprise.name}"]
    if enterprise.credit_code:
        lines.append(f"统一社会信用代码：{enterprise.credit_code}")
    if enterprise.established_date:
        lines.append(f"成立日期：{enterprise.established_date}")
    if enterprise.registered_capital:
        lines.append(f"注册资本：{enterprise.registered_capital}万元")
    if enterprise.employee_count:
        lines.append(f"员工人数：{enterprise.employee_count}人")
    if enterprise.service_customers:
        lines.append(f"服务客户数：{enterprise.service_customers}家")

    # 认证
    certs = []
    if enterprise.haccp_certified:
        certs.append("HACCP")
    if enterprise.iso22000_certified:
        certs.append("ISO22000")
    if enterprise.sc_certified:
        certs.append("SC")
    if certs:
        lines.append(f"体系认证：{'/'.join(certs)}")

    # 冷链资产
    if enterprise.cold_chain_vehicles:
        lines.append(f"冷链车辆：{enterprise.cold_chain_vehicles}辆")
    if enterprise.normal_vehicles:
        lines.append(f"常温车辆：{enterprise.normal_vehicles}辆")
    if enterprise.warehouse_area:
        lines.append(f"仓储面积：{enterprise.warehouse_area}㎡")
    if enterprise.cold_storage_area:
        lines.append(f"冷库面积：{enterprise.cold_storage_area}㎡")
    if enterprise.cold_storage_temp:
        lines.append(f"冷库温度范围：{enterprise.cold_storage_temp}")

    if enterprise.competitive_advantages:
        lines.append(f"\n核心竞争优势：\n{enterprise.competitive_advantages}")

    # 资质证书清单（编号必须原样使用，严禁编造）
    if credentials:
        lines.append("\n== 企业资质证书清单（以下编号必须原样引用，严禁修改或编造）==")
        for cred in credentials:
            parts = [cred.cred_name]
            if cred.cred_no:
                parts.append(f"编号: {cred.cred_no}")
            if cred.expiry_date:
                parts.append(f"有效期至: {cred.expiry_date}")
            elif cred.is_permanent:
                parts.append("长期有效")
            if cred.issuing_authority:
                parts.append(f"发证机关: {cred.issuing_authority}")
            lines.append(f"- {'，'.join(parts)}")

    return "\n".join(lines)


def _build_images_info(images: list[ImageAsset]) -> str:
    """构建可用图片信息文本"""
    if not images:
        return "暂无可用图片资源"
    lines = []
    for img in images:
        lines.append(f"- 图片ID:{img.id} | 分类:{img.category} | 标题:{img.title}")
        if img.description:
            lines.append(f"  说明:{img.description}")
    return "\n".join(lines)


class BidGenerationService:
    """投标章节 AI 生成服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _get_domain_requirements(chapter_title: str) -> str:
        """根据章节标题匹配专项 Prompt"""
        domain_map = {
            "冷链": "cold_chain", "配送": "delivery", "食材采购": "cold_chain",
            "质量": "quality_control", "食品安全": "food_safety",
            "人员": "personnel", "培训": "personnel",
            "应急": "emergency", "服务方案": "emergency",
            "报价": "quotation",
        }
        for keyword, domain in domain_map.items():
            if keyword in chapter_title:
                try:
                    return prompt_manager.format_prompt("domain_prompts", domain)
                except Exception:
                    pass
        return "无特定专项要求，请按通用投标文件规范撰写。"

    async def _get_llm_client(self) -> tuple[AsyncOpenAI, str]:
        """获取 LLM 客户端和模型名（多 Provider 路由）"""
        cfg = LLMSelector.get_client_config("bid_section_generate")
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )
        return client, cfg["model"]

    async def _rag_retrieve(self, query: str, tenant_id: int, top_k: int = 5) -> str:
        """RAG 检索知识库"""
        try:
            from app.services.embedding_service import EmbeddingService
            emb_svc = EmbeddingService(self.session)

            # 检索标准条款
            results = await emb_svc.search_similar(
                query=query, tenant_id=tenant_id, top_k=top_k, threshold=0.35,
            )

            if not results:
                return "暂无相关法规/标准参考"

            lines = []
            for r in results:
                title = r.get("doc_title", r.get("title", ""))
                clause_no = r.get("clause_no", "")
                content = r.get("content", "")[:1500]
                prefix = f"【{title}】" if title else ""
                if clause_no:
                    prefix += f"{clause_no} "
                lines.append(f"{prefix}{content}")
            return "\n\n".join(lines)
        except Exception as e:
            return f"知识库检索暂不可用: {str(e)}"

    async def _search_bid_cases(self, query: str, tenant_id: int, top_k: int = 3) -> str:
        """检索历史中标案例"""
        try:
            from app.services.embedding_service import EmbeddingService
            emb_svc = EmbeddingService(self.session)
            results = await emb_svc.search_snippets(
                query=query, tenant_id=tenant_id, top_k=top_k, threshold=0.4,
            )
            if not results:
                return "暂无相似中标案例参考"
            lines = []
            for r in results:
                lines.append(f"【{r.get('chapter_name', '')}】{r.get('content', '')[:400]}")
            return "\n\n".join(lines)
        except Exception:
            return "历史案例检索暂不可用"

    async def init_chapters(
        self, project_id: int, tenant_id: int, user_id: int
    ) -> list[BidChapter]:
        """根据模板初始化项目的章节结构"""
        svc = BidProjectService(self.session)
        project = await svc.get_project(project_id, tenant_id)
        if not project:
            raise ValueError("投标项目不存在")

        # 如果已有章节，不重复创建
        if project.chapters:
            return project.chapters

        templates = get_chapter_templates(project.customer_type)
        chapters = []
        for i, tmpl in enumerate(templates):
            chapter = BidChapter(
                project_id=project_id,
                chapter_no=tmpl["chapter_no"],
                title=tmpl["title"],
                source=tmpl["source"],
                status="draft",
                sort_order=i,
                tenant_id=tenant_id,
                created_by=user_id,
            )
            self.session.add(chapter)
            chapters.append(chapter)

        await self.session.commit()
        for ch in chapters:
            await self.session.refresh(ch)
        return chapters

    async def generate_single_chapter(
        self, project_id: int, chapter_id: int, tenant_id: int
    ) -> BidChapter:
        """生成单个章节的内容"""
        # 加载项目及关联数据
        svc = BidProjectService(self.session)
        project = await svc.get_project(project_id, tenant_id)
        if not project:
            raise ValueError("投标项目不存在")

        # 找到目标章节
        chapter = None
        for ch in project.chapters:
            if ch.id == chapter_id:
                chapter = ch
                break
        if not chapter:
            raise ValueError("投标章节不存在")

        # 跳过非 AI 生成的章节（template/credential 类型）
        if chapter.source not in ("ai", "draft", "template"):
            return chapter

        # 加载企业信息 + 资质证书
        enterprise_info = "企业信息未填写"
        if project.enterprise_id:
            from app.models.credential import Credential
            result = await self.session.execute(
                select(Enterprise).where(Enterprise.id == project.enterprise_id)
            )
            enterprise = result.scalar_one_or_none()
            if enterprise:
                cred_result = await self.session.execute(
                    select(Credential).where(
                        Credential.enterprise_id == enterprise.id,
                        Credential.tenant_id == tenant_id,
                    )
                )
                creds = list(cred_result.scalars().all())
                enterprise_info = _build_enterprise_info(enterprise, creds)

        # 映射评分标准到章节
        requirements = [
            {"content": r.content, "category": r.category,
             "max_score": r.max_score, "score_weight": r.score_weight}
            for r in project.requirements
        ]
        req_mapping = map_requirements_to_chapters(requirements, project.customer_type)
        mapped_reqs = req_mapping.get(chapter.chapter_no, [])

        # 构建章节大纲
        outline = build_chapter_outline(
            chapter.chapter_no, chapter.title, mapped_reqs, project.customer_type
        )

        # 评分标准文本
        scoring_text = "\n".join(
            f"- {r.get('content', '')}" + (f"（{r.get('max_score')}分）" if r.get('max_score') else "")
            for r in mapped_reqs
        ) or "无特定评分标准映射到本章节"

        # 项目信息
        project_info = (
            f"采购方：{project.tender_org or '未知'}（{project.customer_type or '未知'}）\n"
            f"项目名称：{project.project_name}\n"
            f"预算金额：{project.budget_amount or '未知'}元\n"
            f"配送范围：{project.delivery_scope or '未填写'}\n"
            f"配送周期：{project.delivery_period or '未填写'}"
        )

        # RAG 检索
        rag_query = f"{chapter.title} 生鲜食材配送 {project.customer_type or ''}"
        rag_context = await self._rag_retrieve(rag_query, tenant_id)

        # 加载可用图片
        images = []
        if project.enterprise_id:
            img_result = await self.session.execute(
                select(ImageAsset).where(
                    ImageAsset.enterprise_id == project.enterprise_id,
                    ImageAsset.tenant_id == tenant_id,
                ).order_by(ImageAsset.sort_order)
            )
            images = list(img_result.scalars().all())
        images_info = _build_images_info(images)

        # 计算章节评分权重 → 选择 Prompt 版本和深度
        total_score = sum(r.get("max_score", 0) or 0 for r in mapped_reqs)
        score_weight = round(total_score / max(sum(
            (r.max_score or 0) for r in project.requirements if r.category == "scoring"
        ), 1) * 100, 1)
        priority_level = "高优先级" if total_score >= 15 else "中优先级" if total_score >= 8 else "标准"

        # 构建专项要求（根据章节标题匹配）
        domain_requirements = self._get_domain_requirements(chapter.title)

        # 调用 LLM — 优先使用 V3 评分驱动 Prompt
        client, model = await self._get_llm_client()

        try:
            prompt = prompt_manager.format_prompt(
                "bid_generation", "v3_scoring_driven",
                chapter_no=chapter.chapter_no,
                title=chapter.title,
                project_info=project_info,
                enterprise_info=enterprise_info,
                scoring_criteria=scoring_text,
                outline=outline,
                rag_context=rag_context,
                score_weight=score_weight,
                max_score=total_score,
                priority_level=priority_level,
                domain_requirements=domain_requirements,
            )
        except Exception:
            # V3 不可用时降级到 V2
            prompt = prompt_manager.format_prompt(
                "bid_generation", "v2_with_images",
                chapter_no=chapter.chapter_no,
                title=chapter.title,
                project_info=project_info,
                enterprise_info=enterprise_info,
                scoring_criteria=scoring_text,
                outline=outline,
                rag_context=rag_context,
                available_images=images_info,
            )

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=task_config.get("temperature", 0.3),
            max_tokens=task_config.get("max_tokens", 8192),
        )

        content = response.choices[0].message.content or ""

        # ===== Critic 质量闭环（架构红线：AI 生成必须过 Critic） =====
        from app.services.bid_critic_service import BidCriticService

        critic = BidCriticService()
        chapter_meta = {
            "name": chapter.name,
            "chapter_no": chapter.chapter_no,
            "requirements": [r.content for r in project.requirements] if project.requirements else [],
        }
        content, critic_meta = await critic.critic_and_rewrite(
            content, chapter_meta, enterprise
        )

        # 更新章节
        chapter.content = content
        chapter.source = "ai"
        chapter.status = "generated"
        chapter.ai_model_used = model
        chapter.ai_prompt_version = "v2_with_images"
        # 记录 Critic 审查元数据
        if hasattr(chapter, "meta") and isinstance(chapter.meta, dict):
            chapter.meta["critic"] = critic_meta
        await self.session.commit()
        await self.session.refresh(chapter)

        return chapter

    async def generate_all_chapters(
        self, project_id: int, tenant_id: int, user_id: int
    ) -> AsyncGenerator[dict, None]:
        """
        批量生成所有 AI 章节，通过 yield 报告进度。

        用 Semaphore 控制并发数。
        """
        svc = BidProjectService(self.session)
        project = await svc.get_project(project_id, tenant_id)
        if not project:
            raise ValueError("投标项目不存在")

        # 初始化章节（如果没有）
        if not project.chapters:
            await self.init_chapters(project_id, tenant_id, user_id)
            project = await svc.get_project(project_id, tenant_id)

        # 更新项目状态
        project.status = BidProjectStatus.GENERATING.value
        await self.session.commit()

        ai_chapters = [
            ch for ch in project.chapters
            if ch.source in ("ai", "draft", "template") and ch.status != "finalized"
        ]

        total = len(ai_chapters)
        completed = 0
        failed = 0

        yield {"type": "progress", "total": total, "completed": 0, "status": "started"}

        semaphore = asyncio.Semaphore(settings.DOC_GEN_MAX_CONCURRENCY)

        async def gen_one(ch: BidChapter) -> dict:
            async with semaphore:
                try:
                    await self.generate_single_chapter(project_id, ch.id, tenant_id)
                    return {"chapter_no": ch.chapter_no, "title": ch.title, "status": "ok"}
                except Exception as e:
                    return {"chapter_no": ch.chapter_no, "title": ch.title, "status": "error", "error": str(e)}

        # 逐个生成并报告进度（保持顺序）
        for ch in ai_chapters:
            result = await gen_one(ch)
            if result["status"] == "ok":
                completed += 1
            else:
                failed += 1
            yield {
                "type": "progress",
                "total": total,
                "completed": completed,
                "failed": failed,
                "current": result,
            }

        # 更新项目状态
        final_status = BidProjectStatus.GENERATED.value if failed == 0 else BidProjectStatus.FAILED.value
        project = await svc.get_project(project_id, tenant_id)
        if project:
            project.status = final_status
            await self.session.commit()

        yield {
            "type": "done",
            "total": total,
            "completed": completed,
            "failed": failed,
            "status": final_status,
        }
