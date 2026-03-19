"""
行业词库服务测试 — 懒加载 / 缓存 / Prompt 注入 / RAG 上下文
"""
import pytest
from app.services.industry_vocab import IndustryVocabService


class TestIndustryVocab:
    """行业词库服务单元测试"""

    def test_load_coal_excavation(self):
        """加载煤矿掘进词库"""
        data = IndustryVocabService.get_industry("coal_excavation")
        assert data is not None
        assert data["label"] == "煤矿掘进工程"
        assert "锚杆支护" in data["core_keywords"]

    def test_load_municipal_road(self):
        """加载市政道路词库"""
        data = IndustryVocabService.get_industry("municipal_road")
        assert data is not None
        assert data["label"] == "市政道路工程"

    def test_nonexistent_industry(self):
        """不存在的行业 → None"""
        data = IndustryVocabService.get_industry("spaceship_building")
        assert data is None

    def test_list_industries(self):
        """列出所有行业"""
        industries = IndustryVocabService.list_industries()
        assert len(industries) >= 2
        keys = [i["key"] for i in industries]
        assert "coal_excavation" in keys
        assert "municipal_road" in keys

    def test_build_prompt_injection(self):
        """System Prompt 注入片段包含关键内容"""
        text = IndustryVocabService.build_prompt_injection("coal_excavation")
        assert "煤矿掘进工程" in text
        assert "行业术语" in text
        assert "适用规范" in text
        assert "评审关注点" in text
        assert "常见扣分陷阱" in text
        assert "锚杆支护" in text

    def test_build_prompt_injection_nonexistent(self):
        """不存在的行业 → 空字符串"""
        text = IndustryVocabService.build_prompt_injection("no_such_industry")
        assert text == ""

    def test_build_rag_context(self):
        """RAG 上下文包含评审关注点和扣分项"""
        text = IndustryVocabService.build_rag_context("coal_excavation")
        assert "评审关注点" in text
        assert "常见扣分项" in text

    def test_reload(self):
        """热更新重载不报错"""
        IndustryVocabService.reload()
        data = IndustryVocabService.get_industry("coal_excavation")
        assert data is not None

    def test_cache_works(self):
        """二次加载走缓存"""
        IndustryVocabService.reload()  # 清空缓存
        IndustryVocabService.get_industry("coal_excavation")  # 首次加载
        assert IndustryVocabService._cache is not None
        # 再次调用应走缓存（不会为 None）
        data = IndustryVocabService.get_industry("coal_excavation")
        assert data is not None
