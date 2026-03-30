"""
行业词库服务测试 — 生鲜食材配送行业
"""
import pytest
from app.services.industry_vocab import IndustryVocabService


class TestIndustryVocab:
    """行业词库服务单元测试"""

    def test_load_fresh_food(self):
        """加载生鲜食材配送词库"""
        data = IndustryVocabService.get_industry("fresh_food")
        assert data is not None
        assert data["label"] == "生鲜食材配送"
        assert "冷链配送" in data["core_keywords"]
        assert "HACCP" in data["core_keywords"]

    def test_load_school_canteen(self):
        """加载学校食堂词库"""
        data = IndustryVocabService.get_industry("school_canteen")
        assert data is not None
        assert data["label"] == "学校食堂食材配送"

    def test_load_hospital_canteen(self):
        """加载医院食堂词库"""
        data = IndustryVocabService.get_industry("hospital_canteen")
        assert data is not None

    def test_nonexistent_industry(self):
        """不存在的行业 → None"""
        data = IndustryVocabService.get_industry("spaceship_building")
        assert data is None

    def test_list_industries(self):
        """列出所有行业（至少包含 3 个生鲜场景）"""
        industries = IndustryVocabService.list_industries()
        assert len(industries) >= 3
        keys = [i["key"] for i in industries]
        assert "fresh_food" in keys
        assert "school_canteen" in keys

    def test_build_prompt_injection(self):
        """System Prompt 注入片段包含生鲜行业关键内容"""
        text = IndustryVocabService.build_prompt_injection("fresh_food")
        assert "生鲜食材配送" in text
        assert "行业术语" in text
        assert "适用规范" in text
        assert "评审关注点" in text
        assert "冷链" in text
        assert "食品安全" in text

    def test_build_prompt_injection_nonexistent(self):
        """不存在的行业 → 空字符串"""
        text = IndustryVocabService.build_prompt_injection("no_such_industry")
        assert text == ""

    def test_build_rag_context(self):
        """RAG 上下文包含评审关注点和扣分项"""
        text = IndustryVocabService.build_rag_context("fresh_food")
        assert "评审关注点" in text
        assert "常见扣分项" in text

    def test_standards_included(self):
        """生鲜词库包含食品安全法规"""
        data = IndustryVocabService.get_industry("fresh_food")
        standards = data.get("standards", [])
        assert len(standards) >= 5
        # 至少包含食品安全法
        assert any("食品安全法" in s for s in standards)

    def test_scoring_focus_included(self):
        """生鲜词库包含评审关注点"""
        data = IndustryVocabService.get_industry("fresh_food")
        scoring = data.get("scoring_focus", [])
        assert len(scoring) >= 5
        # 冷链温控是核心评审点
        assert any("冷链" in s or "温控" in s for s in scoring)

    def test_reload(self):
        """热更新重载不报错"""
        IndustryVocabService.reload()
        data = IndustryVocabService.get_industry("fresh_food")
        assert data is not None

    def test_cache_works(self):
        """二次加载走缓存"""
        IndustryVocabService.reload()
        IndustryVocabService.get_industry("fresh_food")
        assert IndustryVocabService._cache is not None
        data = IndustryVocabService.get_industry("fresh_food")
        assert data is not None
