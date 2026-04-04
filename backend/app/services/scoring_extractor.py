"""
评分矩阵自动提取器 — 从招标评分标准拆解子项 + 权重推断

两阶段提取:
  1. 规则层: 正则匹配 "XX分"、"满分XX"、编号列表等模式
  2. LLM 层: 对规则未覆盖的复杂条目调 LLM 拆解（走 call_with_fallback）

输入: TenderRequirement(category=scoring) 条目
输出: ScoringMatrix（大项 → 子项 → 分值 → 响应建议）

架构约束:
  - LLM 调用通过 LLMSelector.call_with_fallback 四级容灾
  - DB 查询强制 tenant_id
  - 测试全量 mock LLM
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_selector import LLMSelector
from app.models.bid_project import BidProject, TenderRequirement

logger = logging.getLogger("freshbid.scoring")

# ── 正则模式 ─────────────────────────────────────────

# 匹配分值: "10分"、"满分15分"、"（20分）"、"最高10分"
_SCORE_PATTERN = re.compile(
    r"(?:满分|最���|共|计)?\s*(\d+(?:\.\d+)?)\s*分"
)

# 匹配编号子项: "①xxx ②xxx" 或 "1.xxx 2.xxx" 或 "(1)xxx (2)xxx"
_SUB_ITEM_PATTERNS = [
    re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]([^①②③④⑤⑥⑦⑧⑨⑩\n]{4,})"),
    re.compile(r"[\(（]\d[\)）]\s*([^\(（\n]{4,})"),
    re.compile(r"(?:^|\n)\s*\d+[\.、]\s*(.{4,})"),
]

# 匹配评分档次: "优(10分) 良(8分) 中(5分)" 等
_GRADE_PATTERN = re.compile(
    r"(优秀?|良好?|一般|中等?|差|合格|不合格)\s*[\(（]?\s*(\d+(?:\.\d+)?)\s*分?\s*[\)）]?"
)


# ── 数据模型 ─────────────────────────────────────────

@dataclass
class ScoringSubItem:
    """评分矩阵子项"""
    parent_req_id: int
    sub_item_name: str
    max_score: float = 0.0
    scoring_criteria: str = ""
    response_suggestion: str = ""
    priority: str = "medium"    # high / medium / low
    extraction_method: str = "rule"  # rule / llm


@dataclass
class ScoringMatrix:
    """完整评分矩阵"""
    project_id: int
    total_score: float = 0.0
    items: list[ScoringSubItem] = field(default_factory=list)
    extraction_method: str = "rule"  # rule / llm / hybrid


# ── 规则层提取 ───────────────────────────────────────

def rule_extract_score(text: str) -> Optional[float]:
    """从文本中提取分值"""
    matches = _SCORE_PATTERN.findall(text)
    if matches:
        # 取最大值（通常是满分）
        return max(float(m) for m in matches)
    return None


def rule_extract_sub_items(text: str, parent_req_id: int) -> list[ScoringSubItem]:
    """规则层: 从评分描述中拆解子项"""
    items = []
    total_score = rule_extract_score(text) or 0

    # 尝试各种编号模式
    for pattern in _SUB_ITEM_PATTERNS:
        matches = pattern.findall(text)
        if len(matches) >= 2:  # 至少 2 个子项才认为是有效拆解
            avg_score = total_score / len(matches) if total_score and matches else 0
            for i, match_text in enumerate(matches):
                clean = match_text.strip().rstrip("；;。.")
                sub_score = rule_extract_score(clean) or avg_score
                items.append(ScoringSubItem(
                    parent_req_id=parent_req_id,
                    sub_item_name=clean[:80],
                    max_score=round(sub_score, 1),
                    scoring_criteria=clean,
                    priority=_classify_priority(sub_score),
                    extraction_method="rule",
                ))
            return items

    # 检查评分档次模式
    grades = _GRADE_PATTERN.findall(text)
    if grades:
        items.append(ScoringSubItem(
            parent_req_id=parent_req_id,
            sub_item_name=text[:80],
            max_score=total_score,
            scoring_criteria=f"评分档次: {', '.join(f'{g[0]}({g[1]}分)' for g in grades)}",
            priority=_classify_priority(total_score),
            extraction_method="rule",
        ))
        return items

    # 无法拆解子项，整体作为单条
    if total_score > 0:
        items.append(ScoringSubItem(
            parent_req_id=parent_req_id,
            sub_item_name=text[:80],
            max_score=total_score,
            scoring_criteria=text[:200],
            priority=_classify_priority(total_score),
            extraction_method="rule",
        ))

    return items


def _classify_priority(score: float) -> str:
    if score >= 15:
        return "high"
    elif score >= 8:
        return "medium"
    return "low"


# ── LLM 层提取 ──────────────────────────────────────

_LLM_SYSTEM = """你是招标文件评分标准分析专家。请将以下评分项拆解为子项，输出 JSON 数组。

每个子项格式:
{"name": "子项名称", "max_score": 分值, "criteria": "评分标准", "suggestion": "响应建议"}

规则:
1. 子项分值之和应等于该评分项总分
2. 如果评分��无法拆解，整体作为 1 个子项
3. 只输出 JSON 数组，不要添加任何解释"""


async def llm_extract_sub_items(
    text: str, parent_req_id: int, total_score: float
) -> list[ScoringSubItem]:
    """LLM 层: 对复杂评分标准进行智能拆解"""
    prompt = f"评分项（满分{total_score}分）:\n{text}\n\n请拆解为子项 JSON 数组。"

    async def _do_call(cfg: dict) -> str:
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )
        resp = await client.chat.completions.create(
            model=cfg["model"],
            temperature=0.1,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or "[]"

    try:
        raw = await LLMSelector.call_with_fallback("compliance_check", _do_call)
        # 清理 markdown 代码块标记
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean
        if clean.endswith("```"):
            clean = clean[:-3].strip()

        # 提取 JSON 数组
        json_match = re.search(r"\[.*\]", clean, re.DOTALL)
        if not json_match:
            return []

        parsed = json.loads(json_match.group())
        items = []
        for entry in parsed:
            score = float(entry.get("max_score", 0))
            items.append(ScoringSubItem(
                parent_req_id=parent_req_id,
                sub_item_name=entry.get("name", "")[:80],
                max_score=round(score, 1),
                scoring_criteria=entry.get("criteria", "")[:200],
                response_suggestion=entry.get("suggestion", "")[:200],
                priority=_classify_priority(score),
                extraction_method="llm",
            ))
        return items
    except Exception as e:
        logger.warning(f"[评分提取] LLM 拆解失败: {e}")
        return []


# ── 主服务 ───────────────────────────────────────────

class ScoringExtractor:
    """评分矩阵自动提取器"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def extract(
        self, project_id: int, tenant_id: int
    ) -> ScoringMatrix:
        """提取完整评分矩阵

        流程:
          1. 加载 category=scoring 的 TenderRequirement
          2. 每条先走规则提取
          3. 规则未拆出子项的走 LLM 增强
          4. 汇总为 ScoringMatrix
        """
        matrix = ScoringMatrix(project_id=project_id)

        # 加载评分类要求（绑定 tenant_id）
        requirements = await self._load_scoring_requirements(project_id, tenant_id)
        if not requirements:
            return matrix

        has_llm = False
        for req in requirements:
            # 阶段1: 规则提取
            sub_items = rule_extract_sub_items(req.content, req.id)

            # 阶段2: 规则���法拆解时尝试 LLM
            if not sub_items:
                total = rule_extract_score(req.content) or (req.max_score or 0)
                llm_items = await llm_extract_sub_items(req.content, req.id, total)
                if llm_items:
                    sub_items = llm_items
                    has_llm = True
                else:
                    # 兜底: 整体作为单条
                    sub_items = [ScoringSubItem(
                        parent_req_id=req.id,
                        sub_item_name=req.content[:80],
                        max_score=req.max_score or 0,
                        scoring_criteria=req.content[:200],
                        priority=_classify_priority(req.max_score or 0),
                        extraction_method="fallback",
                    )]

            # 补充响应建议（规则提取的没有建议）
            for item in sub_items:
                if not item.response_suggestion:
                    item.response_suggestion = f"请在相关章节中明确响应「{item.sub_item_name[:30]}」"

            matrix.items.extend(sub_items)

        matrix.total_score = round(sum(it.max_score for it in matrix.items), 1)
        matrix.extraction_method = "hybrid" if has_llm else "rule"

        return matrix

    async def _load_scoring_requirements(
        self, project_id: int, tenant_id: int
    ) -> list:
        """加载评分类招标要求（tenant_id 隔离）"""
        result = await self.session.execute(
            select(TenderRequirement).join(BidProject).where(
                TenderRequirement.project_id == project_id,
                BidProject.tenant_id == tenant_id,
                TenderRequirement.category == "scoring",
            )
        )
        return list(result.scalars().all())
