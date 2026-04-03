"""
Node 6 reviewer 单元测试 — 关键词匹配 + 语义相似度双模式

语义模式使用 mock embed_fn，严禁调用真实 LLM/Embedding API。
"""
import pytest

from app.services.generation.reviewer import (
    review_scoring_coverage,
    ReviewReport,
    ScoringCoverage,
    _extract_keywords,
    _calc_coverage,
    _cosine_similarity,
    _chunk_text,
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


# ═══════════════════════════════════════════════════════════
# 语义相似度工具函数
# ═══════════════════════════════════════════════════════════

class TestCosineSimilarity:

    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.5]
        assert _cosine_similarity(v, v) == pytest.approx(1.0, abs=0.001)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0, abs=0.001)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0, abs=0.001)

    def test_zero_vector(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


class TestChunkText:

    def test_short_text(self):
        chunks = _chunk_text("短文本")
        assert chunks == ["短文本"]

    def test_empty_text(self):
        chunks = _chunk_text("")
        assert chunks == [""]

    def test_long_text_chunks(self):
        text = "A" * 2000
        chunks = _chunk_text(text, chunk_size=800, overlap=200)
        assert len(chunks) > 1
        # 所有块不超过 chunk_size
        assert all(len(c) <= 800 for c in chunks)
        # 合并块覆盖原文
        combined = chunks[0]
        for c in chunks[1:]:
            combined += c[200:]  # 跳过重叠部分
        assert len(combined) >= len(text)


# ═══════════════════════════════════════════════════════════
# 语义覆盖校验（mock embed_fn，严禁真实 API）
# ═══════════════════════════════════════════════════════════

def _make_mock_embed_fn(similarity_map: dict[tuple[str, str], float]):
    """创建 mock embed_fn，根据预设的相似度矩阵返回假向量

    原理：为每个文本分配一个唯一单位向量方向，
    通过调整角度使 cosine similarity 匹配预期值。
    简化实现：直接用文本内容做 hash 生成伪向量。
    """
    import hashlib

    dim = 64

    def _text_to_vec(text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        raw = [float(b) / 255.0 for b in h[:dim]]
        norm = sum(x * x for x in raw) ** 0.5
        return [x / norm for x in raw] if norm > 0 else raw

    async def mock_embed(texts: list[str]) -> list[list[float] | None]:
        return [_text_to_vec(t) for t in texts]

    return mock_embed


def _make_controlled_embed_fn():
    """创建可精确控制相似度的 mock embed_fn

    「冷链」系列文本 → 相似向量方向
    「有机蔬菜」系列文本 → 正交向量方向
    """
    dim = 8

    def _normalize(v):
        norm = sum(x * x for x in v) ** 0.5
        return [x / norm for x in v] if norm > 0 else v

    # 两个正交基向量
    cold_chain_base = _normalize([1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    organic_base = _normalize([0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    meat_base = _normalize([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0])

    keyword_map = {
        "冷链": cold_chain_base,
        "配送": cold_chain_base,
        "温控": cold_chain_base,
        "低温": cold_chain_base,
        "有机": organic_base,
        "蔬菜": organic_base,
        "种植": organic_base,
        "肉类": meat_base,
        "加工": meat_base,
    }

    def _text_to_vec(text: str) -> list[float]:
        # 累加匹配到的基向量
        vec = [0.0] * dim
        matched = False
        for kw, base in keyword_map.items():
            if kw in text:
                vec = [a + b for a, b in zip(vec, base)]
                matched = True
        if not matched:
            # 默认给一个随机方向
            vec = [float(i + 1) for i in range(dim)]
        return _normalize(vec)

    async def mock_embed(texts: list[str]) -> list[list[float] | None]:
        return [_text_to_vec(t) for t in texts]

    return mock_embed


class TestSemanticCoverage:

    @pytest.mark.asyncio
    async def test_semantic_high_similarity(self):
        """语义相似的文本应判定为高覆盖"""
        chapters = [_chapter(content="全程低温冷链配送温控方案，确保食材新鲜")]
        reqs = [_req(1, "冷链配送方案及温控措施", 15.0)]
        embed_fn = _make_controlled_embed_fn()

        report = await review_scoring_coverage(
            chapters, reqs, threshold=0.6, embed_fn=embed_fn
        )

        assert report.overall_coverage >= 0.6
        assert len(report.uncovered_items) == 0

    @pytest.mark.asyncio
    async def test_semantic_low_similarity(self):
        """语义不相关的文本应判定为未覆盖"""
        chapters = [_chapter(content="本公司主营肉类加工业务")]
        reqs = [_req(1, "有机蔬菜种植基地直供方案", 20.0)]
        embed_fn = _make_controlled_embed_fn()

        report = await review_scoring_coverage(
            chapters, reqs, threshold=0.6, embed_fn=embed_fn
        )

        assert len(report.uncovered_items) == 1
        assert "语义相似度" in report.uncovered_items[0].gap_note

    @pytest.mark.asyncio
    async def test_semantic_covered_in_tracking(self):
        """语义模式下 covered_in 正确追踪匹配章节"""
        chapters = [
            _chapter("第三章", content="冷链配送方案低温运输温控"),
            _chapter("第四章", content="有机蔬菜种植基地管理"),
        ]
        reqs = [_req(1, "冷链配送方案及温控措施")]
        embed_fn = _make_controlled_embed_fn()

        report = await review_scoring_coverage(
            chapters, reqs, threshold=0.3, embed_fn=embed_fn
        )

        item = report.scoring_items[0]
        assert "第三章" in item.covered_in

    @pytest.mark.asyncio
    async def test_fallback_on_embed_error(self):
        """embed_fn 抛异常时降级到关键词匹配"""
        async def broken_embed(texts):
            raise RuntimeError("API 不可用")

        chapters = [_chapter(content="冷链配送方案全程温控措施")]
        reqs = [_req(1, "冷链配送方案及温控措施", 15.0)]

        report = await review_scoring_coverage(
            chapters, reqs, threshold=0.6, embed_fn=broken_embed
        )

        # 降级后仍然能产出报告
        assert report.overall_coverage >= 0.0
        assert len(report.scoring_items) == 1

    @pytest.mark.asyncio
    async def test_no_embed_fn_uses_keywords(self):
        """不传 embed_fn 时走关键词路径（向后兼容）"""
        chapters = [_chapter(content="冷链配送方案全程温控措施")]
        reqs = [_req(1, "冷链配送方案及温控措施", 15.0)]

        report = await review_scoring_coverage(chapters, reqs, threshold=0.6)

        assert report.overall_coverage >= 0.6
        assert len(report.scoring_items) == 1

    @pytest.mark.asyncio
    async def test_semantic_weighted_coverage(self):
        """语义模式下整体覆盖率按分值加权"""
        chapters = [_chapter(content="冷链配送低温运输温控方案")]
        reqs = [
            _req(1, "冷链配送方案及温控措施", 20.0),
            _req(2, "有机蔬菜基地直供", 5.0),
        ]
        embed_fn = _make_controlled_embed_fn()

        report = await review_scoring_coverage(
            chapters, reqs, threshold=0.6, embed_fn=embed_fn
        )

        # 高分冷链项覆盖好 + 低分蔬菜项覆盖差 → 加权整体偏高
        assert report.overall_coverage > 0.3
