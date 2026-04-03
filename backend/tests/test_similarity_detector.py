"""
围串标相似度检测器测试 — 纯算法逻辑（Mock DB/Embedding）

严禁调用真实 embedding API，全部使用 mock。
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.similarity_detector import (
    ngram_fingerprint,
    paragraph_hash_match,
    classify_risk,
    _cosine_similarity,
    SimilarityDetector,
    EMBEDDING_DANGER,
    EMBEDDING_WARNING,
    NGRAM_DANGER,
    NGRAM_WARNING,
)


# ═══════════════════════════════════════════════════════════
# 纯算法测试（无外部依赖）
# ═══════════════════════════════════════════════════════════

class TestNgramFingerprint:

    def test_identical_text_returns_one(self):
        """完全相同文本 → 1.0"""
        text = "我公司拥有冷链配送车辆20辆，覆盖全市范围"
        assert ngram_fingerprint(text, text) == 1.0

    def test_completely_different_text(self):
        """完全不同文本 → 接近 0"""
        a = "我公司专注食材配送领域已有十年经验"
        b = "本次招标项目预算金额为三百万元人民币"
        score = ngram_fingerprint(a, b)
        assert score < 0.3

    def test_partially_similar_text(self):
        """部分相似文本 → 中间值"""
        a = "我公司拥有冷链配送车辆20辆，全程温控保障食品安全"
        b = "我公司拥有冷链配送车辆15辆，全程GPS监控食品运输"
        score = ngram_fingerprint(a, b)
        assert 0.3 < score < 0.9

    def test_empty_text_returns_zero(self):
        """空文本 → 0.0"""
        assert ngram_fingerprint("", "测试") == 0.0
        assert ngram_fingerprint("测试", "") == 0.0
        assert ngram_fingerprint("", "") == 0.0

    def test_short_text_returns_zero(self):
        """过短文本（< n）→ 0.0"""
        assert ngram_fingerprint("AB", "CD", n=3) == 0.0


class TestParagraphHash:

    def test_identical_paragraphs_found(self):
        """完全相同段落被检测到"""
        para = "我公司建立了完善的冷链物流配送体系，拥有专业冷藏车辆和温控仓储设施。"
        text_a = f"第一段内容\n{para}\n第三段内容"
        text_b = f"另一段落\n{para}\n不同的结尾"
        matches = paragraph_hash_match(text_a, text_b)
        assert len(matches) == 1
        assert matches[0] == para

    def test_no_common_paragraphs(self):
        """无重复段落 → 空列表"""
        a = "这是第一份文件的唯一段落，内容完全不同于另一份文件的段落。"
        b = "这是第二份文件的专属段落，包含截然不同的业务描述和技术方案。"
        matches = paragraph_hash_match(a, b)
        assert matches == []

    def test_short_paragraphs_ignored(self):
        """过短段落（< min_length）不参与匹配"""
        a = "短段落\n这是一段足够长的段落内容用于测试精���匹配功能的正确性和可靠性。"
        b = "短段落\n另一段完全不同的长段落内容，和第一份文件没有任何重复。"
        matches = paragraph_hash_match(a, b, min_length=50)
        # "短段落" 太短被忽略，长段落不同 → 无匹配
        assert matches == []

    def test_multiple_matches(self):
        """多段重复全部检出"""
        p1 = "第一段重复内容：我公司拥有完善的食品安全管理体系和质量控制流程。"
        p2 = "第二段重复内容：配送范围覆盖全市各区县，支持冷链和常温双温配送。"
        text_a = f"前言A\n{p1}\n中间A\n{p2}\n结尾A"
        text_b = f"前言B\n{p1}\n中间B\n{p2}\n结尾B"
        matches = paragraph_hash_match(text_a, text_b)
        assert len(matches) == 2


class TestClassifyRisk:

    def test_high_embedding_is_danger(self):
        assert classify_risk(0.90, 0.3, 0) == "danger"

    def test_high_ngram_is_danger(self):
        assert classify_risk(0.5, 0.75, 0) == "danger"

    def test_many_exact_is_danger(self):
        assert classify_risk(0.3, 0.3, 3) == "danger"

    def test_medium_embedding_is_warning(self):
        assert classify_risk(0.72, 0.3, 0) == "warning"

    def test_medium_ngram_is_warning(self):
        assert classify_risk(0.3, 0.55, 0) == "warning"

    def test_one_exact_is_warning(self):
        assert classify_risk(0.3, 0.3, 1) == "warning"

    def test_all_low_is_safe(self):
        assert classify_risk(0.5, 0.3, 0) == "safe"

    def test_zero_is_safe(self):
        assert classify_risk(0.0, 0.0, 0) == "safe"


class TestCosine:

    def test_identical_vectors(self):
        vec = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_empty_vectors(self):
        assert _cosine_similarity([], []) == 0.0
        assert _cosine_similarity([1.0], []) == 0.0


# ═══════════════════════════════════════════════════════��═══
# 集成逻辑测试（Mock DB + Embedding）
# ═══════════════════════════════════════════════════════════

class TestSimilarityDetector:

    @pytest.mark.asyncio
    async def test_no_history_is_safe(self):
        """无历史项目 → safe"""
        session = AsyncMock()
        detector = SimilarityDetector(session)

        # mock: 当前项目有章节
        current_chapters = [
            {"chapter_no": "1", "title": "技术方案", "content": "我公司技术方案如下..."}
        ]
        # mock: 无历史项目
        detector._load_chapters = AsyncMock(return_value=current_chapters)
        detector._load_history_projects = AsyncMock(return_value=[])

        report = await detector.detect(project_id=1, tenant_id=1)
        assert report.safe is True
        assert report.compared_count == 0

    @pytest.mark.asyncio
    async def test_identical_chapters_danger(self):
        """完全相同章节 → danger"""
        session = AsyncMock()
        detector = SimilarityDetector(session)

        same_content = "我公司拥有完善的冷链物流配送��系，配备专业冷藏车辆和温控仓储设施。全程GPS定位追踪，确保食品安全。"
        chapters = [
            {"chapter_no": "1", "title": "技术方案", "content": same_content}
        ]

        detector._load_chapters = AsyncMock(return_value=chapters)
        detector._load_history_projects = AsyncMock(return_value=[(2, "历史项目A")])
        # mock embedding 返回高相似度
        detector._embedding_compare = AsyncMock(return_value=0.95)

        report = await detector.detect(project_id=1, tenant_id=1)
        assert report.safe is False
        assert len(report.danger_items) >= 1
        assert report.danger_items[0].risk_level == "danger"

    @pytest.mark.asyncio
    async def test_different_chapters_safe(self):
        """完全不同章节 → safe"""
        session = AsyncMock()
        detector = SimilarityDetector(session)

        cur = [{"chapter_no": "1", "title": "技术方案", "content": "我公司专注有机蔬菜��植基地直供方案，覆盖学校食堂营养配餐。"}]
        hist = [{"chapter_no": "1", "title": "技术方案", "content": "本次招标项目为医院后勤保障服务，包含中央厨房建设与餐饮管理。"}]

        call_count = [0]
        async def _load_chapters(pid, tid):
            call_count[0] += 1
            return cur if call_count[0] == 1 else hist

        detector._load_chapters = _load_chapters
        detector._load_history_projects = AsyncMock(return_value=[(2, "历史项目B")])
        detector._embedding_compare = AsyncMock(return_value=0.25)

        report = await detector.detect(project_id=1, tenant_id=1)
        assert report.safe is True
        assert len(report.danger_items) == 0

    @pytest.mark.asyncio
    async def test_no_chapters_is_safe(self):
        """当前项目无章节 → safe"""
        session = AsyncMock()
        detector = SimilarityDetector(session)
        detector._load_chapters = AsyncMock(return_value=[])

        report = await detector.detect(project_id=1, tenant_id=1)
        assert report.safe is True

    @pytest.mark.asyncio
    async def test_embedding_failure_graceful(self):
        """embedding 失败时降级为 0，不崩溃"""
        session = AsyncMock()
        detector = SimilarityDetector(session)

        chapters = [
            {"chapter_no": "1", "title": "技术方案", "content": "完全不同的内容A" * 20}
        ]
        hist_chapters = [
            {"chapter_no": "1", "title": "技术方案", "content": "完全不同的内容B" * 20}
        ]

        call_count = [0]
        async def _load_chapters(pid, tid):
            call_count[0] += 1
            return chapters if call_count[0] == 1 else hist_chapters

        detector._load_chapters = _load_chapters
        detector._load_history_projects = AsyncMock(return_value=[(2, "历史项目")])
        # embedding 抛异常
        detector._embedding_compare = AsyncMock(side_effect=Exception("API down"))

        report = await detector.detect(project_id=1, tenant_id=1)
        # 不应崩溃，embedding 失败降级为 0
        assert isinstance(report.safe, bool)
