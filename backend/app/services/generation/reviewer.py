"""
Node 6: 评分点覆盖校验 — 检查每个评分标准是否在章节中被充分响应

支持双模式:
  - 语义相似度（embed_fn 可用时）: embedding 余弦相似度，精度 ~90%
  - 关键词匹配（降级兜底）: 字符串 in 检测，精度 ~60%

输出覆盖率矩阵和未覆盖项清单，供人工审阅或触发回写。
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from app.services.generation.polish_pipeline import PolishResult

logger = logging.getLogger(__name__)

# embed_fn 类型: async (texts: list[str]) -> list[list[float] | None]
EmbedFn = Callable[[list[str]], Awaitable[list[Optional[list[float]]]]]


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


# ── 语义相似度工具 ──────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度（纯 Python，无需 numpy）"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> list[str]:
    """将长文本切分为重叠块，提升 embedding 匹配精度"""
    if not text:
        return [""]
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


async def _semantic_review(
    chapters: list[PolishResult],
    scoring_requirements: list[dict],
    threshold: float,
    embed_fn: EmbedFn,
) -> tuple[list[ScoringCoverage], list[ScoringCoverage]]:
    """语义相似度路径: batch embed + 余弦相似度

    Returns:
        (scoring_items, uncovered_items)
    """
    # 1. 收集所有需要 embed 的文本
    req_texts = [r.get("content", "") for r in scoring_requirements]

    chapter_chunks: list[list[str]] = []  # 按章节分组
    all_chunks: list[str] = []            # 扁平化用于 batch embed
    for ch in chapters:
        chunks = _chunk_text(ch.content or "")
        chapter_chunks.append(chunks)
        all_chunks.extend(chunks)

    # 2. Batch embed（一次 API 调用）
    all_texts = req_texts + all_chunks
    embeddings = await embed_fn(all_texts)

    req_embeddings = embeddings[:len(req_texts)]
    chunk_embeddings_flat = embeddings[len(req_texts):]

    # 将 chunk embeddings 还原为按章节分组
    chunk_embs_by_chapter: list[list[Optional[list[float]]]] = []
    offset = 0
    for chunks in chapter_chunks:
        chunk_embs_by_chapter.append(chunk_embeddings_flat[offset:offset + len(chunks)])
        offset += len(chunks)

    # 3. 逐评分项计算覆盖度
    scoring_items: list[ScoringCoverage] = []
    uncovered_items: list[ScoringCoverage] = []

    for i, req in enumerate(scoring_requirements):
        req_id = req.get("id", 0)
        req_text = req.get("content", "")
        max_score = req.get("max_score")
        req_emb = req_embeddings[i]

        if req_emb is None:
            # embedding 失败，降级到关键词
            keywords = _extract_keywords(req_text)
            all_content = " ".join(ch.content or "" for ch in chapters)
            coverage = _calc_coverage(keywords, all_content)
            covered_in = []
            for ch in chapters:
                if _calc_coverage(keywords, ch.content or "") >= 0.3:
                    covered_in.append(ch.chapter_no)
            gap_note = None
            if coverage < threshold:
                missing = [kw for kw in keywords if kw not in all_content]
                gap_note = f"[关键词降级] 未覆盖: {', '.join(missing[:5])}" if missing else "覆盖度不足"
        else:
            # 语义相似度计算
            best_sim = 0.0
            covered_in = []

            for ch_idx, ch in enumerate(chapters):
                ch_best = 0.0
                for emb in chunk_embs_by_chapter[ch_idx]:
                    if emb is not None:
                        sim = _cosine_similarity(req_emb, emb)
                        ch_best = max(ch_best, sim)
                        best_sim = max(best_sim, sim)
                # 单章覆盖阈值: 0.5（语义匹配门槛低于整体阈值）
                if ch_best >= 0.5:
                    covered_in.append(ch.chapter_no)

            coverage = round(best_sim, 2)
            gap_note = None
            if coverage < threshold:
                gap_note = f"语义相似度 {coverage:.0%}，低于阈值 {threshold:.0%}"

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

    return scoring_items, uncovered_items


# ── 主入口 ────────────────────────────────────────────────

async def review_scoring_coverage(
    chapters: list[PolishResult],
    scoring_requirements: list[dict],
    threshold: float = 0.6,
    embed_fn: Optional[EmbedFn] = None,
) -> ReviewReport:
    """
    评分点覆盖校验节点

    双模式:
      - embed_fn 可用时: embedding 余弦相似度（精度 ~90%）
      - embed_fn 不可用时: 关键词匹配降级（精度 ~60%）

    Args:
        chapters: Node 5 输出的润色后章节
        scoring_requirements: 评分类招标要求
            每项需含: id, content, max_score (可选)
        threshold: 覆盖度阈值，低于此值视为未覆盖
        embed_fn: 可选的批量 embedding 函数，签名:
            async (texts: list[str]) -> list[list[float] | None]

    Returns:
        覆盖校验报告，含整体覆盖率和逐项明细
    """
    # ── 语义路径（优先） ────────────────────────────────
    if embed_fn is not None and scoring_requirements:
        try:
            scoring_items, uncovered_items = await _semantic_review(
                chapters, scoring_requirements, threshold, embed_fn,
            )
            logger.info("评分覆盖校验: 语义模式, %d 项, %d 未覆盖",
                        len(scoring_items), len(uncovered_items))
        except Exception as e:
            logger.warning("语义覆盖校验失败，降级到关键词: %s", e)
            embed_fn = None  # 降级标记

    # ── 关键词路径（降级兜底） ────────────────────────────
    if embed_fn is None:
        # 拼接全部章节内容用于全局匹配
        all_content = " ".join(ch.content or "" for ch in chapters)

        scoring_items = []
        uncovered_items = []

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
                if ch_coverage >= 0.3:
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
