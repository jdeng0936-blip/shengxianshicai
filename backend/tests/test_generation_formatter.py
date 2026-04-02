"""
Node 7 formatter 单元测试 — Mock DB Session + SSE 流验证
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.generation.formatter import (
    format_and_persist,
    stream_generation_progress,
    FormatResult,
    _sse_event,
)
from app.services.generation.reviewer import ReviewReport, ScoringCoverage
from app.services.generation.polish_pipeline import PolishResult


# ── 工厂函数 ──────────────────────────────────────────────

def _chapter(chapter_no="第三章", title="食材采购", content="章节正文内容"):
    return PolishResult(
        chapter_no=chapter_no, title=title,
        content=content, changes_summary="", rounds_applied=1,
    )


def _report(chapters=None, uncovered=None, overall=0.85):
    chs = [_chapter("第三章"), _chapter("第四章")] if chapters is None else chapters
    unc = [] if uncovered is None else uncovered
    return ReviewReport(
        overall_coverage=overall,
        scoring_items=[],
        uncovered_items=unc,
        chapters=chs,
    )


def _mock_session():
    """构造 Mock AsyncSession"""
    session = AsyncMock()
    # mock execute 返回一个带 scalar_one_or_none 的结果
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # 模拟新章节（不存在）
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


# ═══════════════════════════════════════════════════════════
# _sse_event 辅助函数
# ═══════════════════════════════════════════════════════════

class TestSseEvent:

    def test_format(self):
        event = _sse_event({"type": "done", "message": "完成"})
        assert event.startswith("data: ")
        assert event.endswith("\n\n")
        parsed = json.loads(event[6:].strip())
        assert parsed["type"] == "done"

    def test_chinese_no_escape(self):
        event = _sse_event({"text": "中文内容"})
        assert "中文内容" in event  # ensure_ascii=False


# ═══════════════════════════════════════════════════════════
# format_and_persist 主入口
# ═══════════════════════════════════════════════════════════

class TestFormatAndPersist:

    @pytest.mark.asyncio
    @patch("app.services.generation.formatter._persist_chapter")
    async def test_returns_results_for_each_chapter(self, mock_persist):
        """每个章节返回一个 FormatResult"""
        mock_persist.return_value = 100

        results = await format_and_persist(
            session=_mock_session(), project_id=1,
            review_report=_report(),
        )
        assert len(results) == 2
        assert results[0].chapter_no == "第三章"
        assert results[1].chapter_no == "第四章"

    @pytest.mark.asyncio
    @patch("app.services.generation.formatter._persist_chapter")
    async def test_generated_status_default(self, mock_persist):
        """无 uncovered → status=generated"""
        mock_persist.return_value = 100

        results = await format_and_persist(
            session=_mock_session(), project_id=1,
            review_report=_report(uncovered=[]),
        )
        assert all(r.status == "generated" for r in results)

    @pytest.mark.asyncio
    @patch("app.services.generation.formatter._persist_chapter")
    async def test_needs_review_on_uncovered(self, mock_persist):
        """有 uncovered 且 covered_in 为空 → 全部标记 needs_review"""
        mock_persist.return_value = 100

        uncovered = [ScoringCoverage(
            requirement_id=1, requirement_text="有机蔬菜",
            coverage_score=0.1, covered_in=[],
        )]
        results = await format_and_persist(
            session=_mock_session(), project_id=1,
            review_report=_report(uncovered=uncovered),
        )
        assert all(r.status == "needs_review" for r in results)

    @pytest.mark.asyncio
    @patch("app.services.generation.formatter._persist_chapter")
    async def test_word_count_calculated(self, mock_persist):
        """word_count 基于内容长度"""
        mock_persist.return_value = 100
        content = "这是一段测试内容"
        report = _report(chapters=[_chapter(content=content)])

        results = await format_and_persist(
            session=_mock_session(), project_id=1,
            review_report=report,
        )
        assert results[0].word_count == len(content)

    @pytest.mark.asyncio
    @patch("app.services.generation.formatter._persist_chapter")
    async def test_persist_error_graceful(self, mock_persist):
        """持久化失败 → chapter_id=0，不中断"""
        mock_persist.side_effect = RuntimeError("DB 连接失败")

        results = await format_and_persist(
            session=_mock_session(), project_id=1,
            review_report=_report(chapters=[_chapter()]),
        )
        assert len(results) == 1
        assert results[0].chapter_id == 0

    @pytest.mark.asyncio
    @patch("app.services.generation.formatter._persist_chapter")
    async def test_commit_called(self, mock_persist):
        """持久化完成后调用 session.commit"""
        mock_persist.return_value = 100
        session = _mock_session()

        await format_and_persist(
            session=session, project_id=1,
            review_report=_report(),
        )
        session.commit.assert_called_once()


# ═══════════════════════════════════════════════════════════
# stream_generation_progress SSE 流
# ═══════════════════════════════════════════════════════════

class TestStreamGenerationProgress:

    @pytest.mark.asyncio
    @patch("app.services.generation.formatter._persist_chapter")
    async def test_yields_events(self, mock_persist):
        """SSE 流输出 status + chapter_done + done 事件"""
        mock_persist.return_value = 100
        session = _mock_session()

        events = []
        async for event in stream_generation_progress(
            session=session, project_id=1,
            review_report=_report(chapters=[_chapter()]),
        ):
            events.append(event)

        # 至少：1 status + 1 chapter_done + 1 done
        assert len(events) >= 3
        types = [json.loads(e[6:].strip())["type"] for e in events]
        assert "status" in types
        assert "chapter_done" in types
        assert "done" in types

    @pytest.mark.asyncio
    async def test_empty_chapters(self):
        """空章节 → 只输出 done"""
        events = []
        async for event in stream_generation_progress(
            session=_mock_session(), project_id=1,
            review_report=_report(chapters=[]),
        ):
            events.append(event)

        assert len(events) == 1
        parsed = json.loads(events[0][6:].strip())
        assert parsed["type"] == "done"

    @pytest.mark.asyncio
    @patch("app.services.generation.formatter._persist_chapter")
    async def test_progress_increments(self, mock_persist):
        """progress 字段递增"""
        mock_persist.return_value = 100
        chapters = [_chapter("第三章"), _chapter("第四章"), _chapter("第五章")]

        events = []
        async for event in stream_generation_progress(
            session=_mock_session(), project_id=1,
            review_report=_report(chapters=chapters),
        ):
            events.append(event)

        progress_events = [
            json.loads(e[6:].strip()) for e in events
            if "chapter_done" in e
        ]
        progresses = [e["progress"] for e in progress_events]
        assert progresses == [pytest.approx(1/3, abs=0.01),
                              pytest.approx(2/3, abs=0.01),
                              pytest.approx(1.0, abs=0.01)]
