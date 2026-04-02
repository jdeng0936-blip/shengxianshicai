"""
Node 6 reviewer 单元测试 — 纯规则匹配，无外部依赖
"""
import pytest

from app.services.generation.reviewer import (
    review_scoring_coverage,
    ReviewReport,
    ScoringCoverage,
    _extract_keywords,
    _calc_coverage,
)
from app.services.generation.polish_pipeline import PolishResult


# ── 工厂函数 ──────────────────────────────────────────────

def _chapter(chapter_no="第三章", title="食材采购", content="本公司冷链配送方案全程温控"):
    return PolishResult(
        chapter_no=chapter_no, title=title,
        content=content, changes_summary="", rounds_applied=1,
    )


def _req(id=1, content="冷链配送方案及温控措施", max_score=15.0):
    return {"id": id, "content": content, "max_score": max_score}


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════

class TestExtractKeywords:

    def test_basic_split(self):
        kws = _extract_keywords("冷链配送方案及温控措施")
        assert "冷链配送方案" in kws
        assert "温控措施" in kws

    def test_filters_short(self):
        kws = _extract_keywords("有 好 的 冷链方案")
        assert "冷链方案" in kws
        assert "有" not in kws

    def test_empty(self):
        assert _extract_keywords("") == []


class TestCalcCoverage:

    def test_full_coverage(self):
        assert _calc_coverage(["冷链", "温控"], "冷链全程温控方案") == 1.0

    def test_partial_coverage(self):
        assert _calc_coverage(["冷链", "温控", "GPS"], "冷链温控方案") == pytest.approx(2 / 3, abs=0.01)

    def test_zero_coverage(self):
        assert _calc_coverage(["有机蔬菜", "基地直供"], "本公司主营肉类") == 0.0

    def test_no_keywords(self):
        assert _calc_coverage([], "任意内容") == 1.0


# ═══════════════════════════════════════════════════════════
# review_scoring_coverage 主入口
# ═══════════════════════════════════════════════════════════

class TestReviewScoringCoverage:

    @pytest.mark.asyncio
    async def test_full_coverage_report(self):
        """所有评分项被覆盖 → overall_coverage 高"""
        chapters = [_chapter(content="冷链配送方案全程温控措施，GPS实时监控")]
        reqs = [_req(1, "冷链配送方案及温控措施", 15.0)]

        report = await review_scoring_coverage(chapters, reqs)

        assert report.overall_coverage >= 0.6
        assert len(report.uncovered_items) == 0
        assert len(report.scoring_items) == 1

    @pytest.mark.asyncio
    async def test_uncovered_item_flagged(self):
        """评分项未被覆盖 → 进入 uncovered_items"""
        chapters = [_chapter(content="本公司主营肉类加工业务")]
        reqs = [_req(1, "有机蔬菜种植基地直供方案", 20.0)]

        report = await review_scoring_coverage(chapters, reqs, threshold=0.6)

        assert len(report.uncovered_items) == 1
        assert report.uncovered_items[0].requirement_id == 1
        assert report.uncovered_items[0].gap_note is not None

    @pytest.mark.asyncio
    async def test_covered_in_tracks_chapters(self):
        """covered_in 记录覆盖该评分项的章节"""
        chapters = [
            _chapter("第三章", content="冷链配送方案温控措施"),
            _chapter("第四章", content="仓储管理系统"),
        ]
        reqs = [_req(1, "冷链配送方案及温控措施")]

        report = await review_scoring_coverage(chapters, reqs)

        item = report.scoring_items[0]
        assert "第三章" in item.covered_in
        assert "第四章" not in item.covered_in

    @pytest.mark.asyncio
    async def test_no_scoring_reqs(self):
        """无评分项 → overall_coverage=1.0"""
        chapters = [_chapter()]
        report = await review_scoring_coverage(chapters, [])

        assert report.overall_coverage == 1.0
        assert len(report.scoring_items) == 0

    @pytest.mark.asyncio
    async def test_weighted_overall_coverage(self):
        """overall_coverage 按分值加权"""
        chapters = [_chapter(content="冷链配送方案温控措施 人员培训")]
        reqs = [
            _req(1, "冷链配送方案及温控措施", 20.0),  # 高分，被覆盖
            _req(2, "有机蔬菜基地直供", 5.0),          # 低分，未覆盖
        ]

        report = await review_scoring_coverage(chapters, reqs, threshold=0.6)

        # 高分项覆盖好，低分项覆盖差 → 加权后整体偏高
        assert report.overall_coverage > 0.5

    @pytest.mark.asyncio
    async def test_chapters_passthrough(self):
        """chapters 透传到 report"""
        chapters = [_chapter("第三章"), _chapter("第五章")]
        report = await review_scoring_coverage(chapters, [])

        assert len(report.chapters) == 2
        assert report.chapters[0].chapter_no == "第三章"

    @pytest.mark.asyncio
    async def test_custom_threshold(self):
        """自定义阈值影响 uncovered 判定"""
        chapters = [_chapter(content="冷链方案")]
        reqs = [_req(1, "冷链配送方案及温控措施及GPS监控")]

        # 高阈值
        report_high = await review_scoring_coverage(chapters, reqs, threshold=0.9)
        # 低阈值
        report_low = await review_scoring_coverage(chapters, reqs, threshold=0.1)

        assert len(report_high.uncovered_items) >= len(report_low.uncovered_items)
