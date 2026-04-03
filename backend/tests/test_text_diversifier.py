"""
文本差异化引擎测试 — 纯规则层(L1) + LLM层(L2) mock

严禁调用真实 LLM API。
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.text_diversifier import (
    diversify_l1,
    diversify_l2,
    diversify,
    _SYNONYM_MAP,
    _extract_protected_regions,
    _is_protected,
)


# ═══════════════════════════════════════════════════════════
# L1 同义替换
# ═══════════════════════════════════════════════════════════

class TestL1Diversify:

    def test_basic_replacement(self):
        """基础同义替换生效"""
        text = "我公司拥有完善的��链配送方案"
        result, changes = diversify_l1(text, replace_ratio=1.0)
        # 至少有一个词被替换
        assert result != text
        assert len(changes) > 0
        # 所有变更都是 L1 层
        assert all(c.layer == "L1" for c in changes)

    def test_zero_ratio_no_change(self):
        """replace_ratio=0 → 不替换"""
        text = "我公司拥有完善的配送方案"
        result, changes = diversify_l1(text, replace_ratio=0.0)
        assert result == text
        assert len(changes) == 0

    def test_preserves_placeholders(self):
        """占位符 {{xxx}} 不被替换"""
        text = "我公司拥有{{冷链车辆数}}辆���链车"
        result, changes = diversify_l1(text, replace_ratio=1.0)
        # 占位符完整保留
        assert "{{冷链车辆数}}" in result

    def test_preserves_fill_placeholders(self):
        """【请填写xxx】不被替换"""
        text = "我公司拥有【请填写冷链车辆数量】辆冷链车"
        result, changes = diversify_l1(text, replace_ratio=1.0)
        assert "【请填写冷链车辆数量】" in result

    def test_preserves_numbers_with_units(self):
        """数字+单位不被替换"""
        text = "我公司配备20辆冷链车和5000㎡仓库"
        result, changes = diversify_l1(text, replace_ratio=1.0)
        assert "20辆" in result
        assert "5000㎡" in result

    def test_preserves_credential_numbers(self):
        """资质编号不被替换"""
        text = "食品经营许可证编号JY12345678901"
        result, _ = diversify_l1(text, replace_ratio=1.0)
        assert "JY12345678901" in result

    def test_empty_text(self):
        """空文本安全处理"""
        result, changes = diversify_l1("", replace_ratio=1.0)
        assert result == ""
        assert changes == []

    def test_synonym_map_coverage(self):
        """同义词库关键投标术语覆盖"""
        essential_words = ["我公司", "拥有", "确保", "方案", "配送", "冷链", "建立", "管理"]
        for word in essential_words:
            assert word in _SYNONYM_MAP, f"缺少关键词: {word}"
            assert len(_SYNONYM_MAP[word]) >= 2, f"{word} 同义词不足 2 个"


# ═══════════════════════════════════════════════════════════
# 保护区域检测
# ═══════════════════════════════════════════════════════════

class TestProtectedRegions:

    def test_placeholder_detected(self):
        text = "拥有{{冷链车辆数}}辆"
        regions = _extract_protected_regions(text)
        assert len(regions) >= 1

    def test_number_unit_detected(self):
        text = "配备20辆冷链车"
        regions = _extract_protected_regions(text)
        assert len(regions) >= 1

    def test_is_protected_within_range(self):
        regions = [(5, 15)]
        assert _is_protected(7, 3, regions) is True
        assert _is_protected(0, 3, regions) is False
        assert _is_protected(16, 3, regions) is False


# ═══════════════════════════════════════════════════════════
# L2 句法层（Mock LLM）
# ═══════════════════════════════════════════════════════════

class TestL2Diversify:

    @pytest.mark.asyncio
    async def test_l2_calls_llm(self):
        """L2 通过 call_with_fallback 调用 LLM"""
        mock_result = "本单位具备完备的低温物流运送体系，拥有专业冷藏运输车辆及控温仓储设施。"

        with patch(
            "app.services.text_diversifier.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result, ok = await diversify_l2("我公司拥有完善的冷链配送方案" * 10)
            assert ok is True
            assert result == mock_result

    @pytest.mark.asyncio
    async def test_l2_failure_returns_original(self):
        """L2 LLM 失败时返回原文"""
        original = "我公司拥有完善的冷链配送方案" * 10

        with patch(
            "app.services.text_diversifier.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
            side_effect=RuntimeError("全部失败"),
        ):
            result, ok = await diversify_l2(original)
            assert ok is False
            assert result == original

    @pytest.mark.asyncio
    async def test_l2_short_text_skipped(self):
        """短文本（<100 字）跳过 L2"""
        result, ok = await diversify_l2("短文本")
        assert ok is False


# ═══════════════════════════════════════════════════════════
# 全流程 diversify()
# ═══════════════════════════════════════════════════════════

class TestFullDiversify:

    @pytest.mark.asyncio
    async def test_light_mode_l1_only(self):
        """light 模式只执行 L1"""
        text = "我公司拥有完善的冷链配送方案，确保食品安全。" * 5

        with patch(
            "app.services.text_diversifier.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
        ) as mock_llm:
            result = await diversify(text, "light")
            # L1 有替换
            assert result.l1_count > 0
            # L2 未调用
            assert result.l2_applied is False
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_medium_mode_l1_and_l2(self):
        """medium 模式执行 L1 + L2"""
        text = "我公司拥有完善的冷链配送方案，确保食品安全运输。" * 5
        mock_l2 = "本单位具备完备的低温物流运送体系，切实保证膳食安全。" * 5

        with patch(
            "app.services.text_diversifier.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_l2,
        ):
            result = await diversify(text, "medium")
            assert result.l1_count > 0
            assert result.l2_applied is True

    @pytest.mark.asyncio
    async def test_ngram_reduction_positive(self):
        """差异化后 N-gram 与原文的相似度下降"""
        text = "我公司拥有完善的冷链配送方案，确保食品安全。" * 10

        with patch(
            "app.services.text_diversifier.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
            return_value="本单位具备完备的低温物流体系。" * 10,
        ):
            result = await diversify(text, "medium")
            assert result.ngram_reduction > 0

    @pytest.mark.asyncio
    async def test_empty_text_safe(self):
        """空文本安全处理"""
        result = await diversify("", "medium")
        assert result.diversified_text == ""
        assert result.l1_count == 0
