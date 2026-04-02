"""
Node 6: 评分点覆盖校验 — 检查每个评分标准是否在章节中被充分响应

输出覆盖率矩阵和未覆盖项清单，供人工审阅或触发回写。
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.services.generation.polish_pipeline import PolishResult

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class ScoringCoverage:
    """单个评分项的覆盖情况"""
    requirement_id: int
    requirement_text: str
    max_score: Optional[float] = None
    covered_in: list[str] = field(default_factory=list)
    coverage_score: float = 0.0
    gap_note: Optional[str] = None


@dataclass
class ReviewReport:
    """评分覆盖校验报告"""
    overall_coverage: float = 0.0
    scoring_items: list[ScoringCoverage] = field(default_factory=list)
    uncovered_items: list[ScoringCoverage] = field(default_factory=list)
    chapters: list[PolishResult] = field(default_factory=list)


# ── 关键词提取与匹配 ─────────────────────────────────────

def _extract_keywords(text: str) -> list[str]:
    """从评分项文本中提取关键词（2 字以上词段）"""
    return [w for w in re.split(r"[，。、；：\s及与和或的]+", text) if len(w) >= 2]


def _calc_coverage(keywords: list[str], content: str) -> float:
    """计算关键词在内容中的覆盖率 0.0~1.0"""
    if not keywords:
        return 1.0
    matched = sum(1 for kw in keywords if kw in content)
    return matched / len(keywords)


# ── 主入口 ────────────────────────────────────────────────

async def review_scoring_coverage(
    chapters: list[PolishResult],
    scoring_requirements: list[dict],
    threshold: float = 0.6,
) -> ReviewReport:
    """
    评分点覆盖校验节点

    将评分标准逐项与全部章节内容做关键词匹配，计算覆盖度。
    低于阈值的评分项标记为 uncovered，附带补充建议。

    Args:
        chapters: Node 5 输出的润色后章节
        scoring_requirements: 评分类招标要求
            每项需含: id, content, max_score (可选)
        threshold: 覆盖度阈值，低于此值视为未覆盖

    Returns:
        覆盖校验报告，含整体覆盖率和逐项明细
    """
    # 拼接全部章节内容用于全局匹配
    all_content = " ".join(ch.content or "" for ch in chapters)

    scoring_items: list[ScoringCoverage] = []
    uncovered_items: list[ScoringCoverage] = []

    for req in scoring_requirements:
        req_id = req.get("id", 0)
        req_text = req.get("content", "")
        max_score = req.get("max_score")

        keywords = _extract_keywords(req_text)
        coverage = _calc_coverage(keywords, all_content)

        # 找出覆盖该评分项的章节
        covered_in = []
        for ch in chapters:
            ch_content = ch.content or ""
            ch_coverage = _calc_coverage(keywords, ch_content)
            if ch_coverage >= 0.3:  # 至少 30% 关键词命中才算覆盖
                covered_in.append(ch.chapter_no)

        gap_note = None
        if coverage < threshold:
            missing = [kw for kw in keywords if kw not in all_content]
            gap_note = f"未覆盖关键词: {', '.join(missing[:5])}" if missing else "覆盖度不足"

        item = ScoringCoverage(
            requirement_id=req_id,
            requirement_text=req_text,
            max_score=max_score,
            covered_in=covered_in,
            coverage_score=round(coverage, 2),
            gap_note=gap_note,
        )
        scoring_items.append(item)

        if coverage < threshold:
            uncovered_items.append(item)

    # 计算整体覆盖率（按评分分值加权，无分值时等权）
    if scoring_items:
        total_weight = sum(
            (item.max_score or 1.0) for item in scoring_items
        )
        weighted_sum = sum(
            item.coverage_score * (item.max_score or 1.0)
            for item in scoring_items
        )
        overall = round(weighted_sum / max(total_weight, 0.01), 2)
    else:
        overall = 1.0  # 无评分项 → 视为完全覆盖

    return ReviewReport(
        overall_coverage=overall,
        scoring_items=scoring_items,
        uncovered_items=uncovered_items,
        chapters=chapters,
    )
