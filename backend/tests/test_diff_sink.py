"""
差异度下沉服务测试 — 严禁调真实 embedding API

测试：
  1. calc_diff_ratio 各种边界情况
  2. trigger_sink_if_needed 触发/不触发逻辑
"""
import pytest
from unittest.mock import patch, AsyncMock

from app.services.diff_sink import calc_diff_ratio, trigger_sink_if_needed


class TestCalcDiffRatio:
    """差异度计算函数单元测试"""

    def test_identical_texts(self):
        """完全相同 → 0.0"""
        assert calc_diff_ratio("锚杆支护参数", "锚杆支护参数") == 0.0

    def test_empty_original(self):
        """原文为空 → 1.0"""
        assert calc_diff_ratio("", "修改后内容") == 1.0

    def test_empty_revised(self):
        """修改后为空 → 1.0"""
        assert calc_diff_ratio("原始内容", "") == 1.0

    def test_both_empty(self):
        """双空 → 1.0"""
        assert calc_diff_ratio("", "") == 1.0

    def test_small_edit(self):
        """小幅修改 → 较小差异度"""
        original = "IV类围岩推荐锚杆间距800×800mm"
        revised   = "IV类围岩推荐锚杆间距750×750mm"
        ratio = calc_diff_ratio(original, revised)
        assert 0.0 < ratio < 0.5  # 小幅修改

    def test_major_rewrite(self):
        """大幅改写 → 较大差异度"""
        original = "锚杆支护方案"
        revised =  "采用全断面联合支护体系，包含锚杆锚索喷浆三层复合支护结构"
        ratio = calc_diff_ratio(original, revised)
        assert ratio > 0.3  # 大幅改写

    def test_result_range(self):
        """结果在 0~1 之间"""
        ratio = calc_diff_ratio("abc", "xyz")
        assert 0.0 <= ratio <= 1.0


class TestTriggerSink:
    """下沉触发逻辑测试"""

    @patch("app.services.diff_sink.asyncio")
    def test_triggers_when_above_threshold(self, mock_asyncio):
        """差异度超阈值 → 触发 create_task"""
        # 大幅差异的文本对
        ratio = trigger_sink_if_needed(
            original_text="短文本",
            revised_text="这是一段完全不同的很长的修订内容，与原文差异极大",
            chapter_no="3.1",
            chapter_title="支护设计",
            project_id=1,
            tenant_id=1,
        )
        assert ratio is not None
        assert ratio > 0.10
        mock_asyncio.create_task.assert_called_once()

    @patch("app.services.diff_sink.asyncio")
    def test_no_trigger_when_below_threshold(self, mock_asyncio):
        """差异度低于阈值 → 不触发"""
        ratio = trigger_sink_if_needed(
            original_text="IV类围岩推荐锚杆间距800×800mm，排距800mm",
            revised_text="IV类围岩推荐锚杆间距800×800mm，排距850mm",
            chapter_no="3.1",
            chapter_title="支护设计",
            project_id=1,
            tenant_id=1,
        )
        assert ratio is not None
        # 小改动不触发
        mock_asyncio.create_task.assert_not_called()
