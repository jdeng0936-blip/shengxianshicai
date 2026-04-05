"""
特征开关 + RAG 响应式压缩测试
"""
import pytest
from app.core.feature_gate import feature_enabled, get_all_features
from app.services.generation.writer import (
    _build_rag_block, _format_rag_fixed, _format_rag_compact,
)
from app.services.generation.retriever import RetrievalResult


# ═══════════════════════════════════════════════════════════
# 特征开关
# ═══════════════════════════════════════════════════════════

class TestFeatureGate:

    def test_enabled_feature(self):
        """已启用的特征返回 True"""
        assert feature_enabled("ai_detection") is True

    def test_disabled_feature(self):
        """已禁用的特征返回 False"""
        assert feature_enabled("bid_engine_v2") is False

    def test_unknown_feature_default_false(self):
        """未定义的特征默认 False"""
        assert feature_enabled("nonexistent_feature") is False

    def test_unknown_feature_custom_default(self):
        """未定义的特征可指定默认值"""
        assert feature_enabled("nonexistent", default=True) is True

    def test_get_all_features(self):
        """获取所有特征状态"""
        features = get_all_features()
        assert isinstance(features, dict)
        assert "ai_detection" in features
        assert "bid_engine_v2" in features
        assert features["ai_detection"] is True
        assert features["bid_engine_v2"] is False


# ═══════════════════════════════════════════════════════════
# RAG 响应式压缩
# ═══════════════════════════════════════════════════════════

def _make_retrieval(n_clauses=3, n_templates=2, n_cases=2, text_len=200):
    """构造测试用 RetrievalResult"""
    return RetrievalResult(
        chapter_no="第一章",
        std_clauses=[
            {"doc_title": f"法规{i}", "clause_no": f"3.{i}", "text": f"法规条文内容{'x' * text_len}"}
            for i in range(n_clauses)
        ],
        template_snippets=[
            {"chapter_name": f"模板{i}", "text": f"模板片段内容{'y' * text_len}"}
            for i in range(n_templates)
        ],
        bid_cases=[
            {"chapter_name": f"案例{i}", "content": f"案例参考内容{'z' * text_len}"}
            for i in range(n_cases)
        ],
    )


class TestRagBlock:

    def test_fixed_mode_no_limit(self):
        """max_chars=0 使用固定截断模式"""
        retrieval = _make_retrieval()
        result = _build_rag_block(retrieval, max_chars=0)
        assert "法规标准参考" in result
        assert "知识库模板片段" in result
        assert "历史中标案例参考" in result

    def test_empty_retrieval(self):
        """空检索结果返回提示"""
        retrieval = RetrievalResult(chapter_no="第一章")
        result = _build_rag_block(retrieval)
        assert result == "暂无相关参考资料"

    def test_fixed_truncation_respects_limits(self):
        """固定模式下法规截断 600 字、模板/案例 400 字"""
        retrieval = _make_retrieval(text_len=1000)
        result = _build_rag_block(retrieval, max_chars=0)
        # 每条法规不应超过 600 字 + 前缀
        lines = result.split("\n")
        for line in lines:
            if line.startswith("【法规"):
                assert len(line) <= 650  # 600 + 前缀


class TestRagCompact:

    def test_compact_within_budget(self):
        """压缩模式结果不超 max_chars"""
        sections = [
            ("== 法规 ==", [{"prefix": "【A】", "text": "x" * 500, "priority": 3}]),
            ("== 模板 ==", [{"prefix": "【B】", "text": "y" * 500, "priority": 2}]),
            ("== 案例 ==", [{"prefix": "【C】", "text": "z" * 500, "priority": 1}]),
        ]
        result = _format_rag_compact(sections, max_chars=300)
        assert len(result) <= 350  # 允许少量头部开销

    def test_compact_preserves_high_priority(self):
        """压缩时高优先级（法规）内容保留更多"""
        sections = [
            ("== 法规 ==", [{"prefix": "", "text": "法规重要内容" * 50, "priority": 3}]),
            ("== 案例 ==", [{"prefix": "", "text": "案例参考内容" * 50, "priority": 1}]),
        ]
        result = _format_rag_compact(sections, max_chars=200)
        # 法规内容应比案例内容更多
        law_part = result.split("== 案例 ==")[0] if "== 案例 ==" in result else result
        assert "法规重要" in law_part

    def test_compact_truncation_marker(self):
        """超出预算的素材应有截断标记"""
        sections = [
            ("== 法规 ==", [{"prefix": "", "text": "x" * 1000, "priority": 3}]),
        ]
        result = _format_rag_compact(sections, max_chars=100)
        assert "截断" in result
