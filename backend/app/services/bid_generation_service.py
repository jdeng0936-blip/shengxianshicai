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
    is_quotation_chapter,
    get_quotation_template,
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


# ══════════════════════════════════════════════════════════════
# P0 安全红线：高风险字段占位符替换（严禁 LLM 编造）
# ══════════════════════════════════════════════════════════════

# 高风险字段映射：占位符 → (enterprise 属性名, 友好名称)
HIGH_RISK_FIELDS_MAP = {
    "{{企业名称}}": ("name", "企业名称"),
    "{{公司名称}}": ("name", "企业名称"),
    "{{统一社会信用代码}}": ("credit_code", "统一社会信用代码"),
    "{{冷链车辆数}}": ("cold_chain_vehicles", "冷链车辆数量"),
    "{{车辆数量}}": ("cold_chain_vehicles", "冷链车辆数量"),
    "{{常温车辆数}}": ("normal_vehicles", "常温车辆数量"),
    "{{仓储面积}}": ("warehouse_area", "仓储面积"),
    "{{冷库面积}}": ("cold_storage_area", "冷库面积"),
    "{{员工人数}}": ("employee_count", "员工人数"),
    "{{注册资本}}": ("registered_capital", "注册资本"),
    "{{服务客户数}}": ("service_customers", "服务客户数"),
}

# LLM System Prompt 安全约束（追加到所有生成场景）
_SAFETY_CONSTRAINT = (
    "\n\n【安全约束 — 绝对红线】\n"
    "禁止推断或编造以下字段：资质证书编号、车辆数量、仓储面积、人员姓名、合同金额、业绩数据。\n"
    "如信息不在提供的企业数据中，必须使用{{字段名}}占位符（如{{冷链车辆数}}、{{仓储面积}}），"
    "绝不允许自行填写或推断数字。"
)


def replace_high_risk_fields(
    content: str,
    enterprise: Optional[Enterprise] = None,
    credentials: list = None,
) -> str:
    """高风险字段后置替换：用 DB 真实值替换占位符

    规则:
      - 有 DB 值 → 替换为真实值
      - 无 DB 值 → 保留 【请填写XXX】 提示，绝不推断
      - 资质证书编号从 credentials 列表中按名称模糊匹配

    Args:
        content: LLM 生成的原始内容
        enterprise: Enterprise 实例（可为 None）
        credentials: Credential 列表（可为 None）

    Returns:
        替换后的内容
    """
    if not content:
        return content

    # 1. 替换企业字段占位符
    for placeholder, (attr_name, friendly_name) in HIGH_RISK_FIELDS_MAP.items():
        if placeholder in content:
            value = getattr(enterprise, attr_name, None) if enterprise else None
            if value is not None and str(value).strip():
                # 数字类型加单位
                replacement = str(value)
                if attr_name in ("cold_chain_vehicles", "normal_vehicles"):
                    replacement = f"{value}辆"
                elif attr_name in ("warehouse_area", "cold_storage_area"):
                    replacement = f"{value}㎡"
                elif attr_name == "employee_count":
                    replacement = f"{value}人"
                elif attr_name == "registered_capital":
                    replacement = f"{value}万元"
                elif attr_name == "service_customers":
                    replacement = f"{value}家"
                content = content.replace(placeholder, replacement)
            else:
                content = content.replace(placeholder, f"【请填写{friendly_name}】")

    # 2. 替换资质证书编号占位符
    if credentials:
        for cred in credentials:
            cert_placeholder = f"{{{{{cred.cred_name}编号}}}}"
            if cert_placeholder in content and cred.cred_no:
                content = content.replace(cert_placeholder, cred.cred_no)

    # 3. 兜底：捕获任何残留的 {{xxx}} 占位符，标记为待填写
    import re
    content = re.sub(
        r"\{\{([^}]+)\}\}",
        lambda m: f"【请填写{m.group(1)}】",
        content,
    )

    return content


# ══════════════════════════════════════════════════════════════
# P1 正则审计：检测 LLM 绕过占位符直写的敏感数字
# ══════════════════════════════════════════════════════════════

import re as _re
import logging as _logging

_audit_logger = _logging.getLogger("freshbid.audit")

# 敏感数字模式：捕获 LLM 可能直写的具体数值
_SENSITIVE_PATTERNS = [
    # 车辆数量："拥有15辆冷链车"、"配备冷藏车20台"
    (_re.compile(r"(?:拥有|配备|具备|现有|共计|共有)\s*(\d+)\s*辆.*?(?:冷链|冷藏|配送)"), "车辆数量"),
    (_re.compile(r"(?:冷链|冷藏|配送)(?:车辆?|车)\s*(\d+)\s*(?:辆|台)"), "车辆数量"),
    # 仓储面积："仓库面积5000平方米"、"冷库2000㎡"
    (_re.compile(r"(?:仓库|仓储|冷库|库房)(?:面积)?\s*(\d+(?:\.\d+)?)\s*(?:平方米|㎡|平米|m²)"), "仓储面积"),
    # 员工人数："员工300人"、"团队成员200余名"
    (_re.compile(r"(?:员工|人员|团队|配送员|司机)\s*(\d{2,})\s*(?:人|名|位|余人|余名)"), "员工人数"),
    # 注册资本："注册资本1000万元"
    (_re.compile(r"注册资(?:本|金)\s*(\d+(?:\.\d+)?)\s*(?:万元|元|万)"), "注册资本"),
    # 资质编号模式："许可证号JY12345"、"证书编号SC2024001"
    (_re.compile(r"(?:许可证号?|编号|证号|证书号)[：:\s]*([A-Z]{1,5}\d{6,})"), "资质编号"),
]


def audit_sensitive_numbers(
    content: str,
    enterprise: Optional[Enterprise] = None,
) -> list[dict]:
    """扫描 LLM 生成内容中直写的敏感数字，返回不匹配项

    Returns:
        [{"field": "车辆数量", "found": "15", "expected": "10", "match": "拥有15辆冷链车"}, ...]
        空列表表示未发现异常
    """
    alerts = []
    for pattern, field_name in _SENSITIVE_PATTERNS:
        for m in pattern.finditer(content):
            found_value = m.group(1)
            expected = _get_expected_value(field_name, enterprise)
            # 有 DB 值且不一致 → 高风险
            if expected is not None and str(found_value) != str(expected):
                alert = {
                    "field": field_name,
                    "found": found_value,
                    "expected": str(expected),
                    "match": m.group(0),
                    "risk": "mismatch",
                }
                alerts.append(alert)
                _audit_logger.warning(
                    f"[敏感数字审计] {field_name}不一致: "
                    f"文中={found_value} DB={expected} | '{m.group(0)}'"
                )
            # 无 DB 值但 LLM 编造了具体数字 → 中风险
            elif expected is None and field_name != "资质编号":
                alert = {
                    "field": field_name,
                    "found": found_value,
                    "expected": None,
                    "match": m.group(0),
                    "risk": "fabricated",
                }
                alerts.append(alert)
                _audit_logger.warning(
                    f"[敏感数字审计] 疑似编造{field_name}: "
                    f"'{m.group(0)}'（无企业数据可核实）"
                )
    return alerts


def _get_expected_value(field_name: str, enterprise: Optional[Enterprise]) -> Optional[str]:
    """从企业实体获取对应字段的期望值"""
    if not enterprise:
        return None
    mapping = {
        "车辆数量": enterprise.cold_chain_vehicles,
        "仓储面积": enterprise.warehouse_area,
        "员工人数": getattr(enterprise, "employee_count", None),
        "注册资本": enterprise.registered_capital,
    }
    val = mapping.get(field_name)
    return str(val) if val is not None else None


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
        """获取 LLM 客户端和模型名（多 Provider 路由 + 熔断跳过）"""
        cfg = LLMSelector.get_client_config("bid_section_generate")
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )
        return client, cfg["model"]

    async def _call_llm_with_fallback(self, messages: list[dict], **kwargs) -> str:
        """带自动容灾的 LLM 调用（遍历 fallback 链）"""
        temperature = kwargs.pop("temperature", LLMSelector.get_temperature("bid_section_generate"))
        max_tokens = kwargs.pop("max_tokens", LLMSelector.get_max_tokens("bid_section_generate"))

        async def _do_call(cfg: dict) -> str:
            client = AsyncOpenAI(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"] or None,
            )
            resp = await client.chat.completions.create(
                model=cfg["model"],
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            return resp.choices[0].message.content or ""

        return await LLMSelector.call_with_fallback("bid_section_generate", _do_call)

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
        self, project_id: int, chapter_id: int, tenant_id: int,
        on_progress=None,
    ) -> BidChapter:
        """生成单个章节的内容

        Args:
            on_progress: 可选的异步回调 async (phase: str, detail: str) -> None,
                         用于向 WebSocket 广播节点级进度。
        """
        async def _emit(phase: str, detail: str = ""):
            if on_progress:
                await on_progress(phase, detail)

        await _emit("data_load", "加载项目与企业数据")
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

        # P0: 报价类章节强制空表策略 — 不调用 LLM
        if is_quotation_chapter(chapter.chapter_no, chapter.title):
            chapter.content = get_quotation_template()
            chapter.source = "template"
            chapter.status = "generated"
            chapter.source_tags = "template"
            chapter.ai_ratio = 0.0
            await self.session.commit()
            await self.session.refresh(chapter)
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
        await _emit("rag_retrieve", "知识库向量检索")
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

        await _emit("prompt_build", "Prompt 策略构建")
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

        await _emit("llm_generate", f"调用 LLM 生成草稿 ({model})")
        # 脱敏：发往云端 LLM 前 mask，返回后 unmask
        from app.services.desensitize_service import DesensitizeGateway
        gateway = DesensitizeGateway(tenant_id=tenant_id)
        masked_prompt, desens_mapping = gateway.mask(prompt)

        # LLM 参数通过 LLMSelector 获取（严禁硬编码）
        gen_temperature = LLMSelector.get_temperature("bid_section_generate")
        gen_max_tokens = LLMSelector.get_max_tokens("bid_section_generate")

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SAFETY_CONSTRAINT},
                {"role": "user", "content": masked_prompt},
            ],
            temperature=gen_temperature,
            max_tokens=gen_max_tokens,
        )

        content = gateway.unmask(
            response.choices[0].message.content or "", desens_mapping
        )

        # ===== Critic 质量闭环（架构红线：AI 生成必须过 Critic） =====
        await _emit("critic_review", "Critic 五项质量审查")
        from app.services.bid_critic_service import BidCriticService

        critic = BidCriticService()
        chapter_meta = {
            "name": chapter.name,
            "chapter_no": chapter.chapter_no,
            "requirements": [r.content for r in project.requirements] if project.requirements else [],
            "credentials": [
                {"cred_name": c.cred_name, "cred_no": c.cred_no, "expiry_date": c.expiry_date}
                for c in creds
            ] if creds else [],
        }
        content, critic_meta = await critic.critic_and_rewrite(
            content, chapter_meta, enterprise
        )

        # ===== P0 安全红线：高风险字段后置替换 =====
        await _emit("safety_replace", "高风险字段后置替换")
        ai_raw_content = content  # 保留 AI 原始输出用于 ai_ratio 计算
        creds_for_replace = creds if project.enterprise_id else None
        ent_for_replace = enterprise if project.enterprise_id else None
        content = replace_high_risk_fields(content, ent_for_replace, creds_for_replace)

        # P1: 正则审计 — 检测 LLM 绕过占位符直写的敏感数字
        audit_alerts = audit_sensitive_numbers(content, enterprise)
        if audit_alerts:
            await _emit("audit_warning", f"发现 {len(audit_alerts)} 个敏感数字异常")

        # 计算 ai_ratio（替换越多，AI 原创占比越低）
        orig_len = len(ai_raw_content)
        replaced_len = len(content)
        ai_ratio = min(1.0, replaced_len / orig_len) if orig_len > 0 else 0.0

        # 确定 source_tags
        source_tags = ["ai_generated"]
        if ent_for_replace:
            source_tags.append("company_db")

        # 持久化
        await _emit("persist", "写入数据库")
        # 更新章节
        chapter.content = content
        chapter.source = "ai"
        chapter.status = "generated"
        chapter.ai_model_used = model
        chapter.ai_prompt_version = "v2_with_images"
        chapter.ai_ratio = ai_ratio
        chapter.source_tags = ",".join(source_tags)
        # 记录 Critic 审查元数据 + 敏感数字审计
        if hasattr(chapter, "meta") and isinstance(chapter.meta, dict):
            chapter.meta["critic"] = critic_meta
            if audit_alerts:
                chapter.meta["audit_alerts"] = audit_alerts
        await self.session.commit()
        await self.session.refresh(chapter)

        return chapter

    async def generate_single_chapter_stream(
        self, project_id: int, chapter_id: int, tenant_id: int
    ) -> AsyncGenerator[str, None]:
        """流式生成单个章节 — SSE 事件流，各阶段推送状态 + 最终打字机效果

        事件格式 (SSE data 行):
            {"type": "status", "text": "阶段描述..."}
            {"type": "content", "text": "6字符分片"}
            {"type": "done", "chapter_id": 123}
            {"type": "error", "message": "..."}
        """
        import json as _json

        def _evt(data: dict) -> str:
            return f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"

        try:
            yield _evt({"type": "status", "text": "加载项目与企业信息..."})

            svc = BidProjectService(self.session)
            project = await svc.get_project(project_id, tenant_id)
            if not project:
                yield _evt({"type": "error", "message": "投标项目不存在"})
                return

            chapter = None
            for ch in project.chapters:
                if ch.id == chapter_id:
                    chapter = ch
                    break
            if not chapter:
                yield _evt({"type": "error", "message": "投标章节不存在"})
                return

            if chapter.source not in ("ai", "draft", "template"):
                yield _evt({"type": "done", "chapter_id": chapter_id, "text": "非AI章节，跳过"})
                return

            # 加载企业信息 + 资质
            enterprise = None
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

            yield _evt({"type": "status", "text": "RAG 知识检索中..."})

            # 映射评分标准
            requirements = [
                {"content": r.content, "category": r.category,
                 "max_score": r.max_score, "score_weight": r.score_weight}
                for r in project.requirements
            ]
            req_mapping = map_requirements_to_chapters(requirements, project.customer_type)
            mapped_reqs = req_mapping.get(chapter.chapter_no, [])

            outline = build_chapter_outline(
                chapter.chapter_no, chapter.title, mapped_reqs, project.customer_type
            )
            scoring_text = "\n".join(
                f"- {r.get('content', '')}" + (f"（{r.get('max_score')}分）" if r.get('max_score') else "")
                for r in mapped_reqs
            ) or "无特定评分标准映射到本章节"

            project_info = (
                f"采购方：{project.tender_org or '未知'}（{project.customer_type or '未知'}）\n"
                f"项目名称：{project.project_name}\n"
                f"预算金额：{project.budget_amount or '未知'}元\n"
                f"配送范围：{project.delivery_scope or '未填写'}\n"
                f"配送周期：{project.delivery_period or '未填写'}"
            )

            rag_query = f"{chapter.title} 生鲜食材配送 {project.customer_type or ''}"
            rag_context = await self._rag_retrieve(rag_query, tenant_id)

            # 图片
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

            total_score = sum(r.get("max_score", 0) or 0 for r in mapped_reqs)
            score_weight = round(total_score / max(sum(
                (r.max_score or 0) for r in project.requirements if r.category == "scoring"
            ), 1) * 100, 1)
            priority_level = "高优先级" if total_score >= 15 else "中优先级" if total_score >= 8 else "标准"
            domain_requirements = self._get_domain_requirements(chapter.title)

            yield _evt({"type": "status", "text": "AI 生成章节初稿..."})

            client, model = await self._get_llm_client()
            try:
                prompt = prompt_manager.format_prompt(
                    "bid_generation", "v3_scoring_driven",
                    chapter_no=chapter.chapter_no, title=chapter.title,
                    project_info=project_info, enterprise_info=enterprise_info,
                    scoring_criteria=scoring_text, outline=outline,
                    rag_context=rag_context, score_weight=score_weight,
                    max_score=total_score, priority_level=priority_level,
                    domain_requirements=domain_requirements,
                )
            except Exception:
                prompt = prompt_manager.format_prompt(
                    "bid_generation", "v2_with_images",
                    chapter_no=chapter.chapter_no, title=chapter.title,
                    project_info=project_info, enterprise_info=enterprise_info,
                    scoring_criteria=scoring_text, outline=outline,
                    rag_context=rag_context, available_images=images_info,
                )

            yield _evt({"type": "status", "text": "脱敏处理 → 发送至 LLM..."})

            from app.services.desensitize_service import DesensitizeGateway
            gateway = DesensitizeGateway(tenant_id=tenant_id)
            masked_prompt, desens_mapping = gateway.mask(prompt)

            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": masked_prompt}],
                temperature=0.3, max_tokens=8192,
            )
            content = gateway.unmask(
                response.choices[0].message.content or "", desens_mapping
            )

            yield _evt({"type": "status", "text": "Critic 质量审查..."})

            from app.services.bid_critic_service import BidCriticService
            critic = BidCriticService()
            chapter_meta = {
                "name": chapter.title,
                "chapter_no": chapter.chapter_no,
                "requirements": [r.content for r in project.requirements] if project.requirements else [],
                "credentials": [
                    {"cred_name": c.cred_name, "cred_no": c.cred_no, "expiry_date": c.expiry_date}
                    for c in creds
                ] if creds else [],
            }
            content, critic_meta = await critic.critic_and_rewrite(
                content, chapter_meta, enterprise
            )

            rewritten = critic_meta.get("rewritten", False)
            if rewritten:
                yield _evt({"type": "status", "text": "Critic 发现问题，已自动重写修复"})
            else:
                yield _evt({"type": "status", "text": "Critic 审查通过"})

            # 保存到数据库
            chapter.content = content
            chapter.source = "ai"
            chapter.status = "generated"
            chapter.ai_model_used = model
            chapter.ai_prompt_version = "v3_scoring_driven"
            if hasattr(chapter, "meta") and isinstance(chapter.meta, dict):
                chapter.meta["critic"] = critic_meta
            await self.session.commit()
            await self.session.refresh(chapter)

            # 打字机效果流式推送内容
            for i in range(0, len(content), 6):
                chunk = content[i:i + 6]
                yield _evt({"type": "content", "text": chunk})
                await asyncio.sleep(0.01)

            yield _evt({"type": "done", "chapter_id": chapter_id})

        except Exception as e:
            yield _evt({"type": "error", "message": f"生成失败: {str(e)}"})

    async def generate_all_chapters(
        self, project_id: int, tenant_id: int, user_id: int
    ) -> AsyncGenerator[dict, None]:
        """
        批量生成所有 AI 章节，通过 yield 报告进度。
        同时通过 Redis Pub/Sub 广播节点级进度事件供 WebSocket 消费。

        用 Semaphore 控制并发数。
        """
        from app.core.pubsub import publish_progress

        async def _pub(event: dict):
            try:
                await publish_progress(project_id, event)
            except Exception:
                pass  # Pub/Sub 失败不阻塞生成流程

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

        # 广播管线启动
        await _pub({
            "type": "pipeline_start",
            "project_id": project_id,
            "total_chapters": total,
            "chapters": [
                {"chapter_no": ch.chapter_no, "title": ch.title}
                for ch in ai_chapters
            ],
        })

        yield {"type": "progress", "total": total, "completed": 0, "status": "started"}

        semaphore = asyncio.Semaphore(settings.DOC_GEN_MAX_CONCURRENCY)

        async def gen_one(ch: BidChapter, idx: int) -> dict:
            async with semaphore:
                # 广播章节开始
                await _pub({
                    "type": "chapter_start",
                    "chapter_no": ch.chapter_no,
                    "title": ch.title,
                    "chapter_idx": idx,
                })

                # 构建节点级进度回调
                async def _on_progress(phase: str, detail: str = ""):
                    await _pub({
                        "type": "phase",
                        "chapter_no": ch.chapter_no,
                        "phase": phase,
                        "detail": detail,
                    })

                try:
                    result_ch = await self.generate_single_chapter(
                        project_id, ch.id, tenant_id,
                        on_progress=_on_progress,
                    )
                    word_count = len(result_ch.content or "")
                    await _pub({
                        "type": "chapter_done",
                        "chapter_no": ch.chapter_no,
                        "status": "ok",
                        "word_count": word_count,
                    })
                    return {"chapter_no": ch.chapter_no, "title": ch.title, "status": "ok"}
                except Exception as e:
                    await _pub({
                        "type": "chapter_error",
                        "chapter_no": ch.chapter_no,
                        "error": str(e),
                    })
                    return {"chapter_no": ch.chapter_no, "title": ch.title, "status": "error", "error": str(e)}

        # 逐个生成并报告进度（保持顺序）
        for idx, ch in enumerate(ai_chapters):
            result = await gen_one(ch, idx)
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

        # 广播管线完成
        done_event = {
            "type": "pipeline_done",
            "total": total,
            "completed": completed,
            "failed": failed,
            "status": final_status,
        }
        await _pub(done_event)

        yield done_event
