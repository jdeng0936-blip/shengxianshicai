"""
反 AI 检测服务单元测试 — 纯统计分析，无外部依赖
"""
import pytest
from app.services.ai_detection_service import (
    detect_ai_text,
    DetectionReport,
    DimensionScore,
    _split_sentences,
    _tokenize,
    _check_vocabulary_diversity,
    _check_burstiness,
    _check_repetitive_phrases,
    _check_connector_density,
    _check_paragraph_uniformity,
)


# ── 工厂数据 ──────────────────────────────────────────────

# 模拟 AI 生成文本：句长均匀、衔接词密集、词汇重复
AI_LIKE_TEXT = """
本公司具有丰富的生鲜食材配送经验。此外，本公司拥有完善的冷链物流体系。
同时，本公司配备了先进的温控设备。因此，本公司能够确保食材的新鲜度。
值得注意的是，本公司的配送团队经验丰富。具体而言，本公司拥有专业的配送人员。
在此基础上，本公司建立了完善的质量管理体系。进一步，本公司还具有丰富的服务经验。
综上所述，本公司是贵单位食材配送的最佳选择。此外，本公司承诺提供优质的售后服务。
同时，本公司将持续改进服务质量。因此，本公司值得贵单位的信赖与选择。
"""

# 模拟人类写作文本：句长参差、自然过渡、词汇丰富
HUMAN_LIKE_TEXT = """
我们的冷链车队共12辆，包括3吨、5吨两种规格。每车配备GPS定位和实时温度传感器。

去年服务了市第一人民医院、育才小学等23家客户。日均配送量1.2吨生鲜蔬菜，
准时率达到98.7%——这个数字是我们每天凌晨三点出发换来的。

说实话，做食材配送这行不容易。凌晨备货、清晨送达、还要应对突发天气。
但正因为难，才筛掉了那些半途而废的竞争者。

仓库在城东物流园B区，总面积800平方米。其中冷库占320平，能稳定保持0-4℃。
去年底刚花了35万升级了制冷机组，就是为了应对今年夏天的高温挑战。
"""


# ═══════════════════════════════════════════════════════════
# 预处理工具
# ═══════════════════════════════════════════════════════════

class TestPreprocessing:

    def test_split_sentences(self):
        sents = _split_sentences("第一句话。第二句话！短。第三句比较长一些？")
        assert len(sents) >= 2
        assert "第一句话" in sents[0]

    def test_tokenize(self):
        tokens = _tokenize("冷链配送方案，全程温控措施")
        assert "冷链配送方案" in tokens
        assert "全程温控措施" in tokens

    def test_tokenize_filters_short(self):
        tokens = _tokenize("我 的 冷链方案")
        assert "冷链方案" in tokens
        assert "我" not in tokens


# ═══════════════════════════════════════════════════════════
# 各维度检测
# ═══════════════════════════════════════════════════════════

class TestVocabularyDiversity:

    def test_short_text_skip(self):
        tokens = _tokenize("短文本")
        result = _check_vocabulary_diversity(tokens)
        assert result.score == 0

    def test_diverse_text_low_score(self):
        tokens = _tokenize(HUMAN_LIKE_TEXT)
        result = _check_vocabulary_diversity(tokens)
        assert result.score < 50

    def test_repetitive_text_returns_result(self):
        """AI 文本能正常计算词汇多样性（粗粒度分词下 TTR 可能偏高）"""
        tokens = _tokenize(AI_LIKE_TEXT)
        result = _check_vocabulary_diversity(tokens)
        assert result.name == "词汇多样性"
        assert "TTR" in result.detail


class TestBurstiness:

    def test_few_sentences_skip(self):
        sents = _split_sentences("一句话。两句话。")
        result = _check_burstiness(sents)
        assert result.score == 0

    def test_uniform_sentences_high_score(self):
        # 完全等长的句子 → 高风险
        sents = ["这是一个标准长度的测试句子" for _ in range(10)]
        result = _check_burstiness(sents)
        assert result.score >= 50

    def test_varied_sentences_returns_result(self):
        """人类文本按句号分句后能正常计算波动性"""
        sents = _split_sentences(HUMAN_LIKE_TEXT)
        result = _check_burstiness(sents)
        assert result.name == "句长波动性"
        assert "变异系数" in result.detail


class TestRepetitivePhrases:

    def test_short_text_skip(self):
        result = _check_repetitive_phrases("短")
        assert result.score == 0

    def test_ai_text_has_repeats(self):
        result = _check_repetitive_phrases(AI_LIKE_TEXT)
        assert "本公司" in result.detail or result.score > 0


class TestConnectorDensity:

    def test_short_text_skip(self):
        result = _check_connector_density("短文本")
        assert result.score == 0

    def test_ai_text_high_density(self):
        result = _check_connector_density(AI_LIKE_TEXT)
        assert result.score >= 40  # AI 文本衔接词密集

    def test_human_text_low_density(self):
        result = _check_connector_density(HUMAN_LIKE_TEXT)
        assert result.score < 40


class TestParagraphUniformity:

    def test_few_paragraphs_skip(self):
        result = _check_paragraph_uniformity(["一段", "两段"])
        assert result.score == 0

    def test_uniform_paragraphs_high(self):
        paras = ["A" * 100 for _ in range(5)]
        result = _check_paragraph_uniformity(paras)
        assert result.score >= 60

    def test_varied_paragraphs_low(self):
        paras = ["短段。", "A" * 200, "B" * 50, "C" * 300 + "结尾段落，很长"]
        paras = [p for p in paras if len(p) >= 10]
        if len(paras) >= 3:
            result = _check_paragraph_uniformity(paras)
            assert result.score < 60


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

class TestDetectAiText:

    def test_short_text(self):
        report = detect_ai_text("太短了")
        assert report.overall_score == 0
        assert report.risk_level == "low"

    def test_ai_text_high_risk(self):
        report = detect_ai_text(AI_LIKE_TEXT)
        assert report.overall_score > 30
        assert report.risk_level in ("medium", "high")
        assert len(report.dimensions) == 5

    def test_human_text_low_risk(self):
        report = detect_ai_text(HUMAN_LIKE_TEXT)
        assert report.overall_score < 50
        assert report.risk_level in ("low", "medium")

    def test_report_has_suggestions(self):
        report = detect_ai_text(AI_LIKE_TEXT)
        suggestions = [d.suggestion for d in report.dimensions if d.suggestion]
        assert len(suggestions) > 0

    def test_ai_higher_than_human(self):
        """AI 风格文本的检测分应高于人类风格"""
        ai_report = detect_ai_text(AI_LIKE_TEXT)
        human_report = detect_ai_text(HUMAN_LIKE_TEXT)
        assert ai_report.overall_score > human_report.overall_score

    def test_empty_text(self):
        report = detect_ai_text("")
        assert report.overall_score == 0
