"""
Node 7: 格式化持久化 — 写入 BidChapter.content + SSE 实时推送

流水线终节点，负责将最终内容持久化到数据库并通过 SSE 通知前端。
二进制零入库：本节点仅写入纯文本到 PostgreSQL，不存储任何二进制文件。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncGenerator, Optional

from sqlalchemy import select

from app.services.generation.reviewer import ReviewReport

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 覆盖率阈值：低于此值标记为 needs_review
_REVIEW_THRESHOLD = 0.6


@dataclass
class FormatResult:
    """格式化输出"""
    chapter_id: int = 0
    chapter_no: str = ""
    title: str = ""
    word_count: int = 0
    status: str = "generated"


# ── 持久化核心 ────────────────────────────────────────────

async def _persist_chapter(
    session: AsyncSession,
    project_id: int,
    chapter_no: str,
    title: str,
    content: str,
    status: str,
    has_warning: bool,
) -> int:
    """将章节内容写入/更新 BidChapter 表，返回 chapter_id"""
    from app.models.bid_project import BidChapter

    # 查找已有章节
    result = await session.execute(
        select(BidChapter).where(
            BidChapter.project_id == project_id,
            BidChapter.chapter_no == chapter_no,
        )
    )
    chapter = result.scalar_one_or_none()

    if chapter:
        chapter.content = content
        chapter.title = title
        chapter.status = status
        chapter.source = "ai"
        chapter.has_warning = has_warning
    else:
        chapter = BidChapter(
            project_id=project_id,
            chapter_no=chapter_no,
            title=title,
            content=content,
            source="ai",
            status=status,
            has_warning=has_warning,
        )
        session.add(chapter)

    await session.flush()
    return chapter.id


# ── SSE 事件构建 ──────────────────────────────────────────

def _sse_event(data: dict) -> str:
    """构建 SSE 格式事件字符串"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── 主入口 ────────────────────────────────────────────────

async def format_and_persist(
    session: AsyncSession,
    project_id: int,
    review_report: ReviewReport,
    sse_enabled: bool = True,
) -> list[FormatResult]:
    """
    格式化持久化节点

    将校验通过的章节内容写入 BidChapter 表，更新状态为 generated。
    覆盖率不足的章节标记为 needs_review。

    Args:
        session: 数据库会话
        project_id: 投标项目 ID
        review_report: Node 6 输出的覆盖校验报告
        sse_enabled: 是否通过 SSE 推送进度（本函数不产生 SSE，由 stream 版本处理）

    Returns:
        各章节的持久化结果
    """
    # 构建未覆盖章节集合
    uncovered_chapters = set()
    for item in review_report.uncovered_items:
        for ch_no in item.covered_in:
            uncovered_chapters.add(ch_no)
    # 没有覆盖任何章节的评分项 → 标记所有章节为 needs_review
    for item in review_report.uncovered_items:
        if not item.covered_in:
            uncovered_chapters.update(
                ch.chapter_no for ch in review_report.chapters
            )

    results: list[FormatResult] = []

    for ch in review_report.chapters:
        content = ch.content or ""
        has_warning = ch.chapter_no in uncovered_chapters
        status = "needs_review" if has_warning else "generated"

        try:
            chapter_id = await _persist_chapter(
                session=session,
                project_id=project_id,
                chapter_no=ch.chapter_no,
                title=ch.title,
                content=content,
                status=status,
                has_warning=has_warning,
            )
        except Exception as e:
            logger.error("章节 %s 持久化失败: %s", ch.chapter_no, e)
            chapter_id = 0

        results.append(FormatResult(
            chapter_id=chapter_id,
            chapter_no=ch.chapter_no,
            title=ch.title,
            word_count=len(content),
            status=status,
        ))

    await session.commit()
    return results


async def stream_generation_progress(
    session: AsyncSession,
    project_id: int,
    review_report: ReviewReport,
) -> AsyncGenerator[str, None]:
    """
    SSE 流式推送入口

    逐章持久化并推送进度事件，供 FastAPI StreamingResponse 使用。

    Args:
        session: 数据库会话
        project_id: 投标项目 ID
        review_report: Node 6 输出的覆盖校验报告

    Yields:
        SSE 格式字符串: "data: {...}\\n\\n"
    """
    total = len(review_report.chapters)
    if total == 0:
        yield _sse_event({"type": "done", "message": "无章节需要处理"})
        return

    yield _sse_event({"type": "status", "text": "开始持久化章节内容..."})

    uncovered_chapters = set()
    for item in review_report.uncovered_items:
        if not item.covered_in:
            uncovered_chapters.update(
                ch.chapter_no for ch in review_report.chapters
            )
        for ch_no in item.covered_in:
            uncovered_chapters.add(ch_no)

    for i, ch in enumerate(review_report.chapters):
        content = ch.content or ""
        has_warning = ch.chapter_no in uncovered_chapters
        status = "needs_review" if has_warning else "generated"

        try:
            chapter_id = await _persist_chapter(
                session=session,
                project_id=project_id,
                chapter_no=ch.chapter_no,
                title=ch.title,
                content=content,
                status=status,
                has_warning=has_warning,
            )

            yield _sse_event({
                "type": "chapter_done",
                "chapter_no": ch.chapter_no,
                "title": ch.title,
                "status": status,
                "chapter_id": chapter_id,
                "progress": round((i + 1) / total, 2),
            })
        except Exception as e:
            yield _sse_event({
                "type": "error",
                "chapter_no": ch.chapter_no,
                "message": str(e),
            })

    await session.commit()
    yield _sse_event({
        "type": "done",
        "message": f"全部 {total} 章节持久化完成",
        "overall_coverage": review_report.overall_coverage,
    })
