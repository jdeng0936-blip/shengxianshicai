"""
投标合规检查服务 — 废标项 + 资格要求 + 评分覆盖率检查

检查维度:
  1. 废标项（disqualification）— 最高优先级：对照企业资质+章节内容判定是否满足
  2. 资格要求（qualification）— 比对企业已有证照，找出缺口
  3. 评分覆盖（scoring）— 检查评分标准是否在章节中被充分响应
  4. 技术要求（technical）— 检查关键技术要求是否在章节中被提及
  5. 商务要求（commercial）— 检查商务条款是否被响应

架构:
  - 第一层：规则型检查（关键词/资质匹配），快速且确定性高
  - 第二层：LLM 语义审查，对 warning 项做精细判定（通过 LLMSelector 路由）
  - 检查结果写入 TenderRequirement.compliance_status / compliance_note
"""
import json
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.llm_selector import LLMSelector
from app.models.bid_project import BidProject, TenderRequirement, BidChapter
from app.models.enterprise import Enterprise
from app.models.credential import Credential
from app.services.bid_project_service import BidProjectService


# 资格要求关键词 → 资质类型映射
_QUAL_KEYWORD_MAP = {
    "营业执照": ["business_license"],
    "食品经营许可": ["food_license"],
    "食品生产许可": ["sc"],
    "SC认证": ["sc"],
    "HACCP": ["haccp"],
    "ISO22000": ["iso22000"],
    "ISO 22000": ["iso22000"],
    "动物防疫": ["animal_quarantine"],
    "冷链运输": ["cold_chain_transport"],
    "冷链": ["cold_chain_transport"],
    "健康证": ["health_certificate"],
    "公众责任险": ["liability_insurance"],
    "责任保险": ["liability_insurance"],
    "质量检验": ["quality_inspection"],
    "检测报告": ["quality_inspection"],
    "有机认证": ["organic_cert"],
    "绿色食品": ["green_food"],
    "业绩": ["performance"],
    "中标通知": ["performance"],
    "合同": ["performance"],
    "荣誉": ["award"],
}


class ComplianceResult:
    """单条检查结果"""
    def __init__(self, req_id: int, status: str, note: str):
        self.req_id = req_id
        self.status = status  # passed / failed / warning
        self.note = note


class BidComplianceService:
    """投标合规检查服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def check(self, project_id: int, tenant_id: int) -> dict:
        """
        执行全量合规检查。

        Returns:
            {
                "total": int, "passed": int, "failed": int, "warning": int,
                "results": [{"id", "category", "content", "status", "note"}, ...]
            }
        """
        svc = BidProjectService(self.session)
        project = await svc.get_project(project_id, tenant_id)
        if not project:
            raise ValueError("投标项目不存在")

        # 加载企业资质
        credentials = []
        enterprise = None
        if project.enterprise_id:
            ent_result = await self.session.execute(
                select(Enterprise).where(
                    Enterprise.id == project.enterprise_id,
                    Enterprise.tenant_id == tenant_id,  # 安全: 强制租户隔离
                )
            )
            enterprise = ent_result.scalar_one_or_none()

            cred_result = await self.session.execute(
                select(Credential).where(
                    Credential.enterprise_id == project.enterprise_id,
                    Credential.tenant_id == tenant_id,
                )
            )
            credentials = list(cred_result.scalars().all())

        cred_types = {c.cred_type for c in credentials}
        cred_names = " ".join(c.cred_name for c in credentials).lower()

        # 拼接所有章节内容用于文本搜索
        all_chapter_text = "\n".join(
            (ch.content or "") for ch in project.chapters
        ).lower()

        results: list[ComplianceResult] = []

        for req in project.requirements:
            if req.category == "disqualification":
                r = self._check_disqualification(req, cred_types, cred_names, all_chapter_text, enterprise)
            elif req.category == "qualification":
                r = self._check_qualification(req, cred_types, cred_names, enterprise)
            elif req.category == "scoring":
                r = self._check_scoring(req, all_chapter_text)
            elif req.category == "technical":
                r = self._check_technical(req, all_chapter_text)
            elif req.category == "commercial":
                r = self._check_commercial(req, all_chapter_text)
            else:
                r = ComplianceResult(req.id, "passed", "无需检查")

            results.append(r)

        # ===== 第二层: LLM 语义审查（仅对 warning 项做精细判定）=====
        warning_items = [
            (r, req) for r, req in zip(results, project.requirements)
            if r.status == "warning" and req.category in ("disqualification", "scoring")
        ]
        if warning_items:
            llm_results = await self._llm_semantic_check(
                warning_items, all_chapter_text, credentials
            )
            for (orig_r, req), llm_r in zip(warning_items, llm_results):
                if llm_r:
                    # LLM 结果覆盖原 warning
                    idx = results.index(orig_r)
                    results[idx] = llm_r

        # 写入数据库
        for r, req in zip(results, project.requirements):
            req.compliance_status = r.status
            req.compliance_note = r.note

        await self.session.commit()

        passed = sum(1 for r in results if r.status == "passed")
        failed = sum(1 for r in results if r.status == "failed")
        warning = sum(1 for r in results if r.status == "warning")

        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "warning": warning,
            "results": [
                {
                    "id": r.req_id,
                    "category": next(
                        (req.category for req in project.requirements if req.id == r.req_id), ""
                    ),
                    "content": next(
                        (req.content for req in project.requirements if req.id == r.req_id), ""
                    ),
                    "status": r.status,
                    "note": r.note,
                }
                for r in results
            ],
        }

    def _check_disqualification(
        self,
        req: TenderRequirement,
        cred_types: set[str],
        cred_names: str,
        chapter_text: str,
        enterprise: Optional[Enterprise],
    ) -> ComplianceResult:
        """废标项检查 — 最严格：未通过 → failed"""
        content = req.content.lower()

        # 资质类废标项
        for keyword, types in _QUAL_KEYWORD_MAP.items():
            if keyword.lower() in content:
                if any(t in cred_types for t in types):
                    continue
                return ComplianceResult(
                    req.id, "failed",
                    f"废标风险：要求「{keyword}」但企业资质库中未找到匹配证照，请立即补充"
                )

        # 冷链车辆要求
        if "冷链车" in content or "冷藏车" in content:
            if enterprise and enterprise.cold_chain_vehicles and enterprise.cold_chain_vehicles > 0:
                pass
            else:
                return ComplianceResult(
                    req.id, "failed",
                    "废标风险：要求冷链车辆但企业信息中冷链车辆数为0或未填写"
                )

        # 检查章节中是否有响应
        keywords = self._extract_keywords(req.content)
        matched = sum(1 for kw in keywords if kw.lower() in chapter_text)
        if keywords and matched == 0:
            return ComplianceResult(
                req.id, "warning",
                "废标项关键词在投标章节中未找到明确响应，建议人工复核"
            )

        return ComplianceResult(req.id, "passed", "已通过废标项检查")

    def _check_qualification(
        self,
        req: TenderRequirement,
        cred_types: set[str],
        cred_names: str,
        enterprise: Optional[Enterprise],
    ) -> ComplianceResult:
        """资格要求检查 — 比对资质"""
        content = req.content.lower()

        for keyword, types in _QUAL_KEYWORD_MAP.items():
            if keyword.lower() in content:
                if any(t in cred_types for t in types):
                    return ComplianceResult(req.id, "passed", f"已具备「{keyword}」相关资质")
                # 资格要求未满足是 warning（不一定废标）
                return ComplianceResult(
                    req.id, "warning",
                    f"资格要求「{keyword}」在企业资质库中未找到匹配，建议补充"
                )

        # 通用关键词在企业名称中搜索
        if enterprise and enterprise.name:
            return ComplianceResult(req.id, "passed", "资格要求已确认")

        return ComplianceResult(req.id, "warning", "无法自动判定，建议人工核实")

    def _check_scoring(
        self, req: TenderRequirement, chapter_text: str
    ) -> ComplianceResult:
        """评分标准检查 — 关键词在章节中是否有响应"""
        keywords = self._extract_keywords(req.content)
        if not keywords:
            return ComplianceResult(req.id, "passed", "评分标准已确认")

        matched = sum(1 for kw in keywords if kw.lower() in chapter_text)
        ratio = matched / len(keywords) if keywords else 1.0

        if ratio >= 0.5:
            return ComplianceResult(
                req.id, "passed",
                f"评分关键词覆盖率 {ratio:.0%}（{matched}/{len(keywords)}）"
            )
        elif ratio > 0:
            return ComplianceResult(
                req.id, "warning",
                f"评分关键词覆盖率偏低 {ratio:.0%}（{matched}/{len(keywords)}），建议在相关章节补充响应"
            )
        else:
            return ComplianceResult(
                req.id, "warning",
                f"评分关键词在投标章节中未找到响应，可能影响得分"
            )

    def _check_technical(
        self, req: TenderRequirement, chapter_text: str
    ) -> ComplianceResult:
        """技术要求检查"""
        keywords = self._extract_keywords(req.content)
        matched = sum(1 for kw in keywords if kw.lower() in chapter_text)
        if keywords and matched == 0:
            return ComplianceResult(
                req.id, "warning",
                "技术要求关键词在投标章节中未找到响应，建议补充"
            )
        return ComplianceResult(req.id, "passed", "技术要求已响应")

    def _check_commercial(
        self, req: TenderRequirement, chapter_text: str
    ) -> ComplianceResult:
        """商务要求检查"""
        keywords = self._extract_keywords(req.content)
        matched = sum(1 for kw in keywords if kw.lower() in chapter_text)
        if keywords and matched == 0:
            return ComplianceResult(
                req.id, "warning",
                "商务要求关键词在投标章节中未找到响应，建议补充"
            )
        return ComplianceResult(req.id, "passed", "商务要求已响应")

    async def _llm_semantic_check(
        self,
        items: list[tuple["ComplianceResult", TenderRequirement]],
        chapter_text: str,
        credentials: list[Credential],
    ) -> list[Optional["ComplianceResult"]]:
        """LLM 语义级合规审查（第二层增强）

        对规则层输出 warning 的废标项和评分项，用 LLM 做精细语义匹配。
        降级策略：LLM 调用失败时返回 None（保留原关键词检查结果）。
        """
        if not items:
            return []

        try:
            model = LLMSelector.get_model("compliance_check")
            temperature = LLMSelector.get_temperature("compliance_check")
            max_tokens = LLMSelector.get_max_tokens("compliance_check")
        except (KeyError, ValueError):
            return [None] * len(items)

        # 构建批量检查 prompt
        cred_summary = "、".join(c.cred_name for c in credentials) if credentials else "无资质数据"
        # 截取章节文本前 6000 字（避免超长）
        chapter_excerpt = chapter_text[:6000]

        req_list = "\n".join(
            f"{i+1}. [{req.category}] {req.content}"
            for i, (_, req) in enumerate(items)
        )

        prompt = f"""你是投标合规审查专家。请逐条判断以下招标要求是否在投标文件中被充分响应。

## 企业已有资质
{cred_summary}

## 投标文件内容（摘要）
{chapter_excerpt}

## 待检查的招标要求
{req_list}

## 输出要求
对每条要求，判定 status 和 note：
- status: "passed"（已充分响应）/ "failed"（明确不满足，有废标风险）/ "warning"（部分响应但不充分）
- note: 简要说明判定理由（30字以内）

请严格按以下 JSON 数组格式输出，不要输出其他内容：
[{{"index": 1, "status": "passed", "note": "..."}}, ...]"""

        try:
            client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL or None,
            )
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content or ""

            # 提取 JSON 数组
            import re
            json_match = re.search(r'\[.*\]', text, re.DOTALL)
            if not json_match:
                return [None] * len(items)

            parsed = json.loads(json_match.group())
            results: list[Optional[ComplianceResult]] = []
            for i, (orig_r, req) in enumerate(items):
                entry = next((p for p in parsed if p.get("index") == i + 1), None)
                if entry and entry.get("status") in ("passed", "failed", "warning"):
                    results.append(ComplianceResult(
                        req.id,
                        entry["status"],
                        f"[AI审查] {entry.get('note', '')}"
                    ))
                else:
                    results.append(None)
            return results

        except Exception:
            # LLM 调用失败，静默降级
            return [None] * len(items)

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """从要求文本中提取关键词（简单分词）"""
        import re
        # 移除标点，按中文常用词汇提取
        clean = re.sub(r'[，。、；：""''（）【】《》\s]+', ' ', text)
        # 提取 2-8 字的中文词组
        words = re.findall(r'[\u4e00-\u9fff]{2,8}', clean)
        # 过滤常用停用词
        stop_words = {"需要", "提供", "具有", "具备", "应当", "必须", "投标人", "供应商",
                      "招标文件", "本项目", "要求", "相关", "有效", "合格", "以上",
                      "以下", "或者", "并且", "其中", "对于", "按照", "根据"}
        return [w for w in words if w not in stop_words and len(w) >= 2]
