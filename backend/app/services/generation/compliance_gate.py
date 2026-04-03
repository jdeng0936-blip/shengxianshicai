"""
Node 4: 合规门禁 — L1 格式检查 + L2 语义审查 + L3 废标检测

三层递进检查，L3 为阻断级别：任何 L3 issue 导致 passed=False。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.services.generation.writer import DraftChapter

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────

class ComplianceLevel(str, Enum):
    L1_FORMAT = "format"
    L2_SEMANTIC = "semantic"
    L3_DISQUALIFY = "disqualify"


@dataclass
class ComplianceIssue:
    """单个合规问题"""
    level: ComplianceLevel
    chapter_no: str
    description: str
    suggestion: str
    is_blocking: bool = False  # L3 为 True


@dataclass
class ComplianceReport:
    """合规门禁报告"""
    passed: bool
    issues: list[ComplianceIssue] = field(default_factory=list)
    chapters: list[DraftChapter] = field(default_factory=list)


# ── L1 格式检查 ──────────────────────────────────────────

# 章节最低字数阈值
_MIN_WORD_COUNT = {
    "第一章": 100,
    "第二章": 100,
    "第三章": 500,
    "第四章": 500,
    "第五章": 400,
    "第六章": 400,
    "第七章": 400,
    "第八章": 0,   # 报价章节由引擎填充
    "第九章": 100,
}
_DEFAULT_MIN_WORDS = 200

# 口语化/模糊用语黑名单
_VAGUE_PATTERNS = [
    re.compile(r"按规定"),
    re.compile(r"视情况"),
    re.compile(r"根据实际"),
    re.compile(r"适当的"),
    re.compile(r"相关部门"),
    re.compile(r"有关规定"),
    re.compile(r"等等"),
]


def _check_l1_format(draft: DraftChapter) -> list[ComplianceIssue]:
    """L1 格式检查：字数下限 + 空内容 + 口语化用语"""
    issues = []
    min_words = _MIN_WORD_COUNT.get(draft.chapter_no, _DEFAULT_MIN_WORDS)

    # 空内容或占位符
    if not draft.content or draft.content.startswith("（"):
        if min_words > 0:
            issues.append(ComplianceIssue(
                level=ComplianceLevel.L1_FORMAT,
                chapter_no=draft.chapter_no,
                description=f"{draft.chapter_no} 内容为空或为占位符",
                suggestion="需要生成实际章节内容",
            ))
        return issues

    # 字数不足
    if draft.word_count < min_words:
        issues.append(ComplianceIssue(
            level=ComplianceLevel.L1_FORMAT,
            chapter_no=draft.chapter_no,
            description=f"{draft.chapter_no} 字数不足: {draft.word_count}/{min_words}",
            suggestion=f"建议扩充至 {min_words} 字以上，补充技术细节和量化指标",
        ))

    # 口语化/模糊用语
    for pattern in _VAGUE_PATTERNS:
        matches = pattern.findall(draft.content)
        if matches:
            issues.append(ComplianceIssue(
                level=ComplianceLevel.L1_FORMAT,
                chapter_no=draft.chapter_no,
                description=f"{draft.chapter_no} 包含模糊用语: '{matches[0]}'",
                suggestion=f"将 '{matches[0]}' 替换为具体数值或标准引用",
            ))

    return issues


# ── L2 语义审查 ──────────────────────────────────────────

# 常见法规标准名称及其标准写法（用于校验引用准确性）
_STANDARD_REFS = {
    "食品安全法": "《中华人民共和国食品安全法》",
    "GB/T 22918": "GB/T 22918",
    "GB 31621": "GB 31621",
    "HACCP": "HACCP",
    "ISO22000": "ISO 22000",
    "ISO 22000": "ISO 22000",
}


def _check_l2_semantic(
    draft: DraftChapter,
    requirements: list[dict],
) -> list[ComplianceIssue]:
    """L2 语义审查：法规引用校验 + 评分要求关键词覆盖"""
    issues = []
    content = draft.content or ""

    # 检查评分类要求是否在章节中有所覆盖
    scoring_reqs = [
        r for r in requirements
        if r.get("category") == "scoring" and r.get("chapter_no") == draft.chapter_no
    ]
    for req in scoring_reqs:
        req_text = req.get("content", "")
        max_score = req.get("max_score") or 0
        # 简单关键词提取（取 2 字以上的词段，按标点和常见连接词切分）
        keywords = [w for w in re.split(r"[，。、；：\s及与和或的]+", req_text) if len(w) >= 2]
        matched = sum(1 for kw in keywords if kw in content)
        coverage = matched / max(len(keywords), 1)
        # 按权重动态调整阈值：高分项要求更高覆盖率
        threshold = 0.5 if max_score >= 10 else (0.3 if max_score >= 5 else 0.2)
        if coverage < threshold:
            score_hint = f"（分值{max_score}分，要求覆盖≥{threshold:.0%}）" if max_score else ""
            issues.append(ComplianceIssue(
                level=ComplianceLevel.L2_SEMANTIC,
                chapter_no=draft.chapter_no,
                description=f"评分项覆盖不足({coverage:.0%}){score_hint}: '{req_text[:40]}'",
                suggestion="在章节中补充对该评分项的具体响应内容",
            ))

    return issues


# ── L3 废标检测 ──────────────────────────────────────────

# 废标关键词 → 所需资质类型（复用 bid_compliance_service 的映射逻辑）
_DISQUALIFY_CRED_MAP = {
    "食品经营许可": "food_license",
    "营业执照": "business_license",
    "HACCP": "haccp",
    "ISO22000": "iso22000",
    "ISO 22000": "iso22000",
    "SC认证": "sc",
    "冷链运输": "cold_chain_transport",
    "冷链车": "cold_chain_transport",
    "冷藏车": "cold_chain_transport",
    "健康证": "health_certificate",
}


def _check_l3_disqualify(
    drafts: list[DraftChapter],
    requirements: list[dict],
    enterprise_cred_types: Optional[set[str]] = None,
) -> list[ComplianceIssue]:
    """L3 废标检测：废标项关键词匹配 + 资质缺失检测"""
    issues = []
    cred_types = enterprise_cred_types or set()
    all_content = " ".join(d.content or "" for d in drafts)

    disqualify_reqs = [
        r for r in requirements if r.get("category") == "disqualification"
    ]

    for req in disqualify_reqs:
        req_text = req.get("content", "")

        # 检查是否涉及资质要求
        for keyword, cred_type in _DISQUALIFY_CRED_MAP.items():
            if keyword in req_text and cred_type not in cred_types:
                issues.append(ComplianceIssue(
                    level=ComplianceLevel.L3_DISQUALIFY,
                    chapter_no="全局",
                    description=f"废标风险: 要求 '{keyword}' 但企业缺少对应资质 ({cred_type})",
                    suggestion=f"请确认企业是否持有 {keyword} 相关资质，缺失将导致废标",
                    is_blocking=True,
                ))

        # 检查废标项内容是否在投标文件中被提及/响应
        keywords = [w for w in re.split(r"[，。、；：\s]+", req_text) if len(w) >= 2]
        matched = sum(1 for kw in keywords if kw in all_content)
        coverage = matched / max(len(keywords), 1)
        if coverage < 0.2:
            issues.append(ComplianceIssue(
                level=ComplianceLevel.L3_DISQUALIFY,
                chapter_no="全局",
                description=f"废标项未在投标文件中响应: '{req_text[:50]}'",
                suggestion="必须在对应章节中明确响应该废标项要求",
                is_blocking=True,
            ))

    return issues


# ── L2+: 195号文增强 — 跨章节一致性 ─────────────────────

# 需提取的关键数值模式（名称 → 正则）
_NUMERIC_PATTERNS = {
    "冷链车辆": re.compile(r'冷[链藏]车[辆量]?\s*[:：]?\s*(\d+)\s*[辆台]'),
    "常温车辆": re.compile(r'常温车[辆量]?\s*[:：]?\s*(\d+)\s*[辆台]'),
    "员工人数": re.compile(r'员工[人数]*\s*[:：]?\s*(\d+)\s*[人名]'),
    "仓储面积": re.compile(r'仓[储库]\S*面积\s*[:：]?\s*(\d+)\s*[㎡平方]'),
    "冷库面积": re.compile(r'冷库\S*面积\s*[:：]?\s*(\d+)\s*[㎡平方]'),
    "服务客户": re.compile(r'服务\S*客户\s*[:：]?\s*(\d+)\s*[家户]'),
    "注册资本": re.compile(r'注册资本\s*[:：]?\s*(\d+)\s*万'),
}


def _check_cross_chapter_consistency(
    drafts: list[DraftChapter],
) -> list[ComplianceIssue]:
    """跨章节数据一致性检查（195号文合规要求）

    提取各章节中的关键数值声明，检测同一指标在不同章节中是否矛盾。
    """
    issues = []
    found: dict[str, list[tuple[str, str]]] = {}

    for draft in drafts:
        content = draft.content or ""
        for metric_name, pattern in _NUMERIC_PATTERNS.items():
            matches = pattern.findall(content)
            for val in matches:
                found.setdefault(metric_name, []).append((draft.chapter_no, val))

    for metric_name, entries in found.items():
        values = set(v for _, v in entries)
        if len(values) > 1:
            detail = ", ".join(f"{ch}={v}" for ch, v in entries)
            issues.append(ComplianceIssue(
                level=ComplianceLevel.L2_SEMANTIC,
                chapter_no="跨章节",
                description=f"数据矛盾 [{metric_name}]: {detail}",
                suggestion=f"请统一各章节中 {metric_name} 的数值，确保前后一致",
            ))

    return issues


# ── L2+: 195号文增强 — 资质引用完整性 ────────────────────

# ── L2+: 195号文增强 — 项目上下文一致性 ──────────────────

# 客户类型关键词映射
_CUSTOMER_TYPE_KEYWORDS = {
    "学校": ["学校", "学生", "校园", "食堂", "师生", "教职工", "学期"],
    "医院": ["医院", "患者", "病房", "医疗", "住院", "营养科", "膳食"],
    "政府": ["政府", "机关", "公务", "行政", "办公楼"],
    "企业": ["企业", "员工", "职工", "工厂", "园区", "写字楼"],
    "养老": ["养老", "老人", "护理", "敬老院", "康养"],
    "部队": ["部队", "官兵", "军营", "营区"],
}


def _check_project_context_consistency(
    drafts: list[DraftChapter],
    project_context: Optional[dict] = None,
) -> list[ComplianceIssue]:
    """项目上下文一致性检查（防复制旧标书未更新）

    检测投标文件中引用的项目名称、采购方、服务对象等关键信息
    是否与当前投标项目匹配。

    Args:
        drafts: 章节列表
        project_context: 当前项目元数据，包含:
            - project_name: 项目名称
            - tender_org: 采购方名称
            - customer_type: 客户类型（学校/医院/政府/企业）
            - delivery_scope: 配送范围
    """
    issues = []
    if not project_context:
        return issues

    project_name = project_context.get("project_name", "")
    tender_org = project_context.get("tender_org", "")
    customer_type = project_context.get("customer_type", "")
    all_content = " ".join(d.content or "" for d in drafts)

    # 1. 客户类型冲突检测
    if customer_type:
        current_keywords = _CUSTOMER_TYPE_KEYWORDS.get(customer_type, [])
        for other_type, other_keywords in _CUSTOMER_TYPE_KEYWORDS.items():
            if other_type == customer_type:
                continue
            for kw in other_keywords:
                if kw in all_content:
                    # 排除：当前类型关键词也在同一句中（可能是对比描述）
                    # 仅当其他类型关键词出现且当前类型关键词缺失时才告警
                    has_current_nearby = any(ck in all_content for ck in current_keywords[:3])
                    if not has_current_nearby or all_content.count(kw) >= 3:
                        # 找到出现在哪个章节
                        for d in drafts:
                            if kw in (d.content or ""):
                                issues.append(ComplianceIssue(
                                    level=ComplianceLevel.L2_SEMANTIC,
                                    chapter_no=d.chapter_no,
                                    description=f"客户类型疑似错配: 当前项目为「{customer_type}」类，但 {d.chapter_no} 出现「{kw}」（{other_type}类关键词）",
                                    suggestion=f"请检查是否从{other_type}类项目复制了内容，需将「{kw}」相关描述替换为{customer_type}类场景",
                                ))
                                break  # 同一关键词只报一次
                        break  # 同一类型只报最显著的一个

    # 2. 采购方名称不匹配检测
    if tender_org and len(tender_org) >= 4:
        # 提取文中所有疑似机构名（XX学校/XX医院/XX公司 等）
        org_pattern = re.compile(
            r'[\u4e00-\u9fff]{2,15}(?:学校|小学|中学|大学|医院|公司|局|中心|单位|部门|政府|街道|社区|集团)'
        )
        found_orgs = set(org_pattern.findall(all_content))
        # 过滤掉当前采购方名称及其子串
        foreign_orgs = [
            org for org in found_orgs
            if org not in tender_org and tender_org not in org
            and len(org) >= 4
        ]
        # 检查是否有非当前采购方的具体机构名（出现 2 次以上更可疑）
        for org in foreign_orgs:
            count = all_content.count(org)
            if count >= 2:
                for d in drafts:
                    if org in (d.content or ""):
                        issues.append(ComplianceIssue(
                            level=ComplianceLevel.L3_DISQUALIFY,
                            chapter_no=d.chapter_no,
                            description=f"疑似残留其他项目采购方名称: 「{org}」出现 {count} 次（当前采购方为「{tender_org}」）",
                            suggestion=f"请立即检查并将「{org}」替换为当前采购方「{tender_org}」或删除相关内容，此问题可能导致废标",
                            is_blocking=True,
                        ))
                        break

    # 3. 项目名称残留检测（按标点分句后提取，避免跨句捕获）
    if project_name and len(project_name) >= 6:
        proj_suffixes = ["项目", "采购", "招标", "磋商"]
        foreign_refs: dict[str, int] = {}

        clauses = re.split(r'[，。！？；：\n、（）]', all_content)
        for clause in clauses:
            for suffix in proj_suffixes:
                if suffix not in clause:
                    continue
                idx = clause.index(suffix)
                before = clause[:idx]
                parts = re.findall(r'[\u4e00-\u9fff]+', before)
                if not parts:
                    continue
                # 取紧邻后缀的最后一段中文作为项目名核心
                core = parts[-1]
                candidate = core + suffix
                if (len(candidate) >= 6
                        and candidate not in project_name
                        and project_name not in candidate):
                    foreign_refs[candidate] = foreign_refs.get(candidate, 0) + 1

        # 合并相似候选（取最短的作为代表，避免不同前缀导致分裂）
        merged: dict[str, int] = {}
        sorted_refs = sorted(foreign_refs.keys(), key=len)
        for candidate in sorted_refs:
            # 检查是否是某个已有候选的超集
            found_parent = False
            for existing in list(merged.keys()):
                if existing in candidate:
                    merged[existing] += foreign_refs[candidate]
                    found_parent = True
                    break
            if not found_parent:
                merged[candidate] = foreign_refs[candidate]

        for proj, count in merged.items():
            if count >= 1 and 6 <= len(proj) <= 25:
                for d in drafts:
                    if proj in (d.content or ""):
                        issues.append(ComplianceIssue(
                            level=ComplianceLevel.L3_DISQUALIFY,
                            chapter_no=d.chapter_no,
                            description=f"疑似残留其他项目名称: 「{proj}」出现 {count} 次",
                            suggestion=f"请检查是否应替换为当前项目「{project_name}」",
                            is_blocking=True,
                        ))
                        break

    return issues


_CRED_CHAPTER_MAP = {
    "haccp": {"keywords": ["HACCP", "危害分析", "关键控制点"], "expected_in": ["质量", "安全", "管理"]},
    "iso22000": {"keywords": ["ISO 22000", "ISO22000", "食品安全管理体系"], "expected_in": ["质量", "安全", "管理"]},
    "sc": {"keywords": ["SC认证", "食品生产许可", "SC"], "expected_in": ["资质", "质量", "生产"]},
    "cold_chain_transport": {"keywords": ["冷链", "冷藏运输", "温控"], "expected_in": ["配送", "运输", "冷链"]},
}


def _check_credential_chapter_match(
    drafts: list[DraftChapter],
    enterprise_cred_types: Optional[set[str]] = None,
) -> list[ComplianceIssue]:
    """资质-章节引用匹配验证（195号文合规要求）

    检查企业持有的资质是否在对应章节中被正确引用。
    """
    issues = []
    if not enterprise_cred_types:
        return issues

    for cred_type in enterprise_cred_types:
        mapping = _CRED_CHAPTER_MAP.get(cred_type)
        if not mapping:
            continue

        keywords = mapping["keywords"]
        expected_topics = mapping["expected_in"]

        relevant_chapters = [
            d for d in drafts
            if any(topic in (d.title or "") for topic in expected_topics)
        ]

        if not relevant_chapters:
            continue

        for draft in relevant_chapters:
            content = draft.content or ""
            has_ref = any(kw in content for kw in keywords)
            if not has_ref:
                issues.append(ComplianceIssue(
                    level=ComplianceLevel.L2_SEMANTIC,
                    chapter_no=draft.chapter_no,
                    description=f"企业持有 {cred_type} 资质但 {draft.chapter_no} 未引用",
                    suggestion=f"建议在本章节中引用 {'/'.join(keywords[:2])} 相关认证信息以增强说服力",
                ))

    return issues


# ── 主入口 ────────────────────────────────────────────────

async def check_compliance(
    drafts: list[DraftChapter],
    requirements: list[dict],
    enterprise_cred_types: Optional[set[str]] = None,
    project_context: Optional[dict] = None,
) -> ComplianceReport:
    """
    合规门禁节点

    三层递进检查:
      L1 格式 — 章节编号连续性、标题规范、字数下限、口语化用语
      L2 语义 — 评分项覆盖校验、法规引用准确性
      L3 废标 — 废标项关键词匹配、资质缺失检测

    Args:
        drafts: Node 3 输出的草稿章节
        requirements: 招标要求列表（含 category 字段区分废标/资格/评分）
        enterprise_cred_types: 企业已有资质类型集合，用于 L3 资质匹配

    Returns:
        合规报告，passed=False 时流水线应暂停等待修复
    """
    all_issues: list[ComplianceIssue] = []

    # L1: 逐章格式检查
    for draft in drafts:
        all_issues.extend(_check_l1_format(draft))

    # L2: 逐章语义审查
    for draft in drafts:
        all_issues.extend(_check_l2_semantic(draft, requirements))

    # L2+: 项目上下文一致性（防复制旧标书未更新）
    all_issues.extend(_check_project_context_consistency(drafts, project_context))

    # L2+: 195号文增强 — 跨章节一致性
    all_issues.extend(_check_cross_chapter_consistency(drafts))

    # L2+: 195号文增强 — 资质引用完整性
    all_issues.extend(_check_credential_chapter_match(drafts, enterprise_cred_types))

    # L3: 全局废标检测
    all_issues.extend(_check_l3_disqualify(drafts, requirements, enterprise_cred_types))

    has_blocking = any(issue.is_blocking for issue in all_issues)

    return ComplianceReport(
        passed=not has_blocking,
        issues=all_issues,
        chapters=drafts,
    )
