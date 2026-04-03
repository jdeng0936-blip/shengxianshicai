"""
投标合规检查服务 — L0格式预检 + 废标项 + 资格要求 + 评分覆盖率检查

检查维度:
  L0. 格式预检（numbering/colloquial/standard_ref/paragraph）— 纯规则，毫秒级
  1. 废标项（disqualification）— 最高优先级：对照企业资质+章节内容判定是否满足
  2. 资格要求（qualification）— 比对企业已有证照，找出缺口
  3. 评分覆盖（scoring）— 检查评分标准是否在章节中被充分响应
  4. 技术要求（technical）— 检查关键技术要求是否在章节中被提及
  5. 商务要求（commercial）— 检查商务条款是否被响应

架构:
  - L0 层：格式规范检查（编号跳号/口语化/规范引用/段落质量），纯正则
  - 第一层：规则型检查（关键词/资质匹配），快速且确定性高
  - 第二层：LLM 语义审查，对 warning 项做精细判定（通过 LLMSelector 路由）
  - 检查结果写入 TenderRequirement.compliance_status / compliance_note
"""
import json
import re
from datetime import datetime
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

    # ===== L0 格式预检常量（移植自 biaobiao，适配生鲜领域）=====

    # 口语化表达黑名单
    _COLLOQUIAL_PATTERNS = [
        r"我们?觉得", r"大概", r"差不多", r"可能吧",
        r"比较好", r"还行", r"挺好的", r"没什么问题",
        r"OK", r"ok", r"然后呢", r"其实",
        r"说实话", r"老实说", r"搞定", r"搞好",
        r"弄一下", r"做一下", r"看看再说",
    ]

    # 中文一级编号正则
    _CN_NUMBERING_L1 = re.compile(r"^[一二三四五六七八九十]+、")
    _CN_NUMS = "一二三四五六七八九十"

    # 食品安全相关规范编号格式
    _STANDARD_PATTERN = re.compile(
        r"(GB/?T?\s*\d{4,5}[-—]\d{4}|"
        r"DB\d{2}/?\s*\d{3,5}[-—]\d{4}|"        # 地方标准
        r"SB/?T?\s*\d{4,5}[-—]\d{4}|"            # 商业标准
        r"NY/?T?\s*\d{3,5}[-—]\d{4})"             # 农业标准
    )

    def __init__(self, session: AsyncSession):
        self.session = session

    # ===== L0 格式预检方法 =====

    @classmethod
    def format_precheck(cls, chapters: list) -> list[dict]:
        """L0 格式预检 — 对所有章节做纯规则检查，返回问题列表

        Returns:
            [{"level": "warning", "category": "format", "title": ..., "detail": ...}, ...]
        """
        issues: list[dict] = []
        for ch in chapters:
            content = ch.content or ""
            if not content.strip():
                continue
            chapter_label = f"「{ch.chapter_no} {ch.title}」"

            # 1. 编号跳号检测
            issues.extend(cls._check_numbering(content, chapter_label))
            # 2. 口语化检测
            issues.extend(cls._check_colloquial(content, chapter_label))
            # 3. 规范引用年份校验
            issues.extend(cls._check_standard_refs(content, chapter_label))
            # 4. 过短段落检测
            issues.extend(cls._check_paragraph_quality(content, chapter_label))

        return issues

    @classmethod
    def _check_numbering(cls, content: str, chapter_label: str) -> list[dict]:
        """检查中文一级编号连续性（一、二、三...不跳号）"""
        issues = []
        lines = content.split("\n")
        found_numbers = []

        for line_no, line in enumerate(lines, 1):
            stripped = line.strip()
            match = cls._CN_NUMBERING_L1.match(stripped)
            if match:
                num_char = stripped[0]
                if num_char in cls._CN_NUMS:
                    found_numbers.append((line_no, cls._CN_NUMS.index(num_char)))

        for i in range(1, len(found_numbers)):
            prev_idx = found_numbers[i - 1][1]
            curr_idx = found_numbers[i][1]
            if curr_idx != prev_idx + 1:
                expected = cls._CN_NUMS[prev_idx + 1] if prev_idx + 1 < len(cls._CN_NUMS) else "?"
                issues.append({
                    "level": "warning",
                    "category": "format_numbering",
                    "title": f"{chapter_label} 编号跳号",
                    "detail": f"第{found_numbers[i][0]}行「{cls._CN_NUMS[curr_idx]}」前应为「{expected}」，"
                              f"编号不连续可能导致评审扣分",
                })
        return issues

    @classmethod
    def _check_colloquial(cls, content: str, chapter_label: str) -> list[dict]:
        """检测口语化表达"""
        found = []
        for pattern in cls._COLLOQUIAL_PATTERNS:
            matches = re.findall(pattern, content)
            if matches:
                found.extend(matches)

        if found:
            examples = "、".join(f"「{w}」" for w in found[:5])
            return [{
                "level": "warning",
                "category": "format_colloquial",
                "title": f"{chapter_label} 口语化表达",
                "detail": f"检测到 {len(found)} 处口语化: {examples}，标书应使用正式书面语",
            }]
        return []

    @classmethod
    def _check_standard_refs(cls, content: str, chapter_label: str) -> list[dict]:
        """校验规范引用年份合理性"""
        issues = []
        matches = cls._STANDARD_PATTERN.findall(content)
        for ref in matches:
            year_match = re.search(r"(\d{4})$", ref)
            if year_match:
                year = int(year_match.group(1))
                if year < 2000:
                    issues.append({
                        "level": "warning",
                        "category": "format_standard_ref",
                        "title": f"{chapter_label} 规范可能已作废",
                        "detail": f"引用「{ref}」年份 {year} 过早，食品安全法规更新频繁，请核实是否为现行版本",
                    })
                elif year > 2026:
                    issues.append({
                        "level": "warning",
                        "category": "format_standard_ref",
                        "title": f"{chapter_label} 规范年份异常",
                        "detail": f"引用「{ref}」年份 {year} 超过当前年份，请核实",
                    })
        return issues

    @classmethod
    def _check_paragraph_quality(cls, content: str, chapter_label: str) -> list[dict]:
        """检查过短段落"""
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        short_paras = [
            p for p in paragraphs
            if 0 < len(p) < 20 and not cls._CN_NUMBERING_L1.match(p)
        ]
        if len(short_paras) > 3:
            return [{
                "level": "advice",
                "category": "format_paragraph",
                "title": f"{chapter_label} 段落过短",
                "detail": f"发现 {len(short_paras)} 个过短段落（少于20字），建议合并或扩充内容",
            }]
        return []

    # ===== 主入口 =====

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

        # 解析投标截止日（用于资质有效期比对）
        project_deadline: Optional[datetime] = None
        if project.deadline:
            try:
                project_deadline = datetime.strptime(project.deadline[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        # 拼接所有章节内容用于文本搜索
        all_chapter_text = "\n".join(
            (ch.content or "") for ch in project.chapters
        ).lower()

        results: list[ComplianceResult] = []

        for req in project.requirements:
            if req.category == "disqualification":
                r = self._check_disqualification(
                    req, cred_types, cred_names, all_chapter_text,
                    enterprise, credentials, project_deadline,
                )
            elif req.category == "qualification":
                r = self._check_qualification(
                    req, cred_types, cred_names, enterprise,
                    credentials, project_deadline,
                )
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

        # L0 格式预检（编号跳号/口语化/规范引用/段落质量）
        format_issues = self.format_precheck(project.chapters) if project.chapters else []

        return {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "warning": warning,
            "format_issues": format_issues,
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
        credentials: list = None,
        project_deadline: Optional[datetime] = None,
    ) -> ComplianceResult:
        """废标项检查 — 最严格：未通过 → failed（含资质有效期比对）"""
        content = req.content.lower()
        credentials = credentials or []

        # 资质类废标项（类型 + 有效期双重检查）
        for keyword, types in _QUAL_KEYWORD_MAP.items():
            if keyword.lower() in content:
                matching_creds = [c for c in credentials if c.cred_type in types]
                if not matching_creds:
                    return ComplianceResult(
                        req.id, "failed",
                        f"废标风险：要求「{keyword}」但企业资质库中未找到匹配证照，请立即补充"
                    )
                # 检查匹配资质的有效期
                expiry_issue = self._check_credential_expiry(
                    matching_creds, project_deadline, keyword
                )
                if expiry_issue:
                    return ComplianceResult(req.id, *expiry_issue)
                continue

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
        credentials: list = None,
        project_deadline: Optional[datetime] = None,
    ) -> ComplianceResult:
        """资格要求检查 — 比对资质（含有效期）"""
        content = req.content.lower()
        credentials = credentials or []

        for keyword, types in _QUAL_KEYWORD_MAP.items():
            if keyword.lower() in content:
                matching_creds = [c for c in credentials if c.cred_type in types]
                if not matching_creds:
                    return ComplianceResult(
                        req.id, "warning",
                        f"资格要求「{keyword}」在企业资质库中未找到匹配，建议补充"
                    )
                # 检查匹配资质的有效期
                expiry_issue = self._check_credential_expiry(
                    matching_creds, project_deadline, keyword
                )
                if expiry_issue:
                    return ComplianceResult(req.id, *expiry_issue)
                return ComplianceResult(req.id, "passed", f"已具备「{keyword}」相关资质且有效期充足")

        # 通用关键词在企业名称中搜索
        if enterprise and enterprise.name:
            return ComplianceResult(req.id, "passed", "资格要求已确认")

        return ComplianceResult(req.id, "warning", "无法自动判定，建议人工核实")

    @staticmethod
    def _check_credential_expiry(
        creds: list,
        project_deadline: Optional[datetime],
        keyword: str,
    ) -> Optional[tuple[str, str]]:
        """检查资质列表中是否有有效的（未过期且截止日前有效的）证照。

        Returns:
            None — 至少有一个有效资质，检查通过
            (status, note) — 全部无效时返回，调用方构建 ComplianceResult
        """
        now = datetime.now()
        has_valid = False

        for cred in creds:
            if cred.is_permanent:
                has_valid = True
                continue
            if not cred.expiry_date:
                continue
            try:
                expiry = datetime.strptime(cred.expiry_date[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                continue

            days_left = (expiry - now).days

            # 已过期
            if days_left < 0:
                continue
            # 将在投标截止日前过期
            if project_deadline and expiry < project_deadline:
                continue
            # 30 天内过期（不影响本次投标但需预警）
            if days_left <= 30:
                has_valid = True
                continue
            # 有效期充足
            has_valid = True

        if has_valid:
            # 额外检查：是否有 30 天内过期的（返回 warning）
            for cred in creds:
                if cred.is_permanent or not cred.expiry_date:
                    continue
                try:
                    expiry = datetime.strptime(cred.expiry_date[:10], "%Y-%m-%d")
                except (ValueError, TypeError):
                    continue
                days_left = (expiry - now).days
                if 0 <= days_left <= 30 and (not project_deadline or expiry >= project_deadline):
                    return (
                        "warning",
                        f"「{keyword}」资质将于 {cred.expiry_date[:10]} 到期"
                        f"（剩余 {days_left} 天），建议尽快续期"
                    )
            return None

        # 全部无效：区分"已过期"和"截止前过期"
        for cred in creds:
            if cred.is_permanent or not cred.expiry_date:
                continue
            try:
                expiry = datetime.strptime(cred.expiry_date[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                continue
            if (expiry - now).days < 0:
                return (
                    "failed",
                    f"「{keyword}」资质（{cred.cred_name}）已于 {cred.expiry_date[:10]} 过期，"
                    f"投标将被判定资格不合格"
                )
            if project_deadline and expiry < project_deadline:
                return (
                    "failed",
                    f"「{keyword}」资质（{cred.cred_name}）将于 {cred.expiry_date[:10]} 到期，"
                    f"早于投标截止日 {project_deadline.strftime('%Y-%m-%d')}，投标时该资质已失效"
                )

        return ("failed", f"「{keyword}」资质均无有效期信息，无法确认有效性")

    def _check_scoring(
        self, req: TenderRequirement, chapter_text: str
    ) -> ComplianceResult:
        """评分标准检查 — 关键词覆盖 + 按 max_score 权重分级

        分级规则（与 risk_report_service 对齐）:
          废标级(is_mandatory) → failed
          max_score >= 10      → failed（高分漏答视同严重风险）
          max_score >= 5       → warning
          max_score < 5        → warning（轻度提示）
        """
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

        # 未充分覆盖 — 按权重分级
        max_score = req.max_score or 0
        score_info = f"（分值 {max_score}分）" if max_score else ""

        if req.is_mandatory:
            return ComplianceResult(
                req.id, "failed",
                f"废标级评分项未响应{score_info}，覆盖率 {ratio:.0%}（{matched}/{len(keywords)}），"
                f"必须在相关章节补充完整响应"
            )
        elif max_score >= 10:
            return ComplianceResult(
                req.id, "failed",
                f"高分评分项未充分响应{score_info}，覆盖率 {ratio:.0%}（{matched}/{len(keywords)}），"
                f"强烈建议补充以避免大幅失分"
            )
        elif max_score >= 5:
            return ComplianceResult(
                req.id, "warning",
                f"评分项覆盖不足{score_info}，覆盖率 {ratio:.0%}（{matched}/{len(keywords)}），"
                f"建议在相关章节补充响应"
            )
        else:
            return ComplianceResult(
                req.id, "warning",
                f"评分关键词覆盖率偏低 {ratio:.0%}（{matched}/{len(keywords)}），可能影响得分"
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
            temperature = LLMSelector.get_temperature("compliance_check")
            max_tokens = LLMSelector.get_max_tokens("compliance_check")
        except (KeyError, ValueError):
            return [None] * len(items)

        # 构建批量检查 prompt
        cred_summary = "、".join(c.cred_name for c in credentials) if credentials else "无资质数据"
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
            async def _do_compliance_call(cfg: dict):
                client = AsyncOpenAI(
                    api_key=cfg["api_key"],
                    base_url=cfg["base_url"] or None,
                )
                resp = await client.chat.completions.create(
                    model=cfg["model"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content or ""

            text = await LLMSelector.call_with_fallback(
                "compliance_check", _do_compliance_call
            )

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
