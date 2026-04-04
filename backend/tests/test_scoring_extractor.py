"""
评分矩阵自动提取器测试 — 规则层 + LLM层 mock

严禁调用真实 LLM API。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.scoring_extractor import (
    rule_extract_score,
    rule_extract_sub_items,
    llm_extract_sub_items,
    ScoringExtractor,
    ScoringSubItem,
    _classify_priority,
)


# ═══════════════════════════════════════════════════════════
# 分值提取
# ═══════════════════════════════════════════════════════════

class TestRuleExtractScore:

    def test_simple_score(self):
        """'10分' → 10.0"""
        assert rule_extract_score("技术方案（10分）") == 10.0

    def test_full_score(self):
        """'满分15分' → 15.0"""
        assert rule_extract_score("满分15分") == 15.0

    def test_max_score(self):
        """'最高20分' → 20.0"""
        assert rule_extract_score("最高20分") == 20.0

    def test_multiple_scores_takes_max(self):
        """多个分值取最大"""
        assert rule_extract_score("优(10分) 良(8分) 中(5分)") == 10.0

    def test_no_score(self):
        """无分值 → None"""
        assert rule_extract_score("技术方案要求详细") is None

    def test_decimal_score(self):
        """小数分值"""
        assert rule_extract_score("满分7.5分") == 7.5


# ═══════════════════════════════════════════════════════════
# 子项拆解（规则层）
# ═══════════════════════════════════════════════════════════

class TestRuleExtractSubItems:

    def test_circled_numbers(self):
        """①②③ 编号子项拆解"""
        text = "技术方案（满分20分）：①冷链配送方案 ②温控措施 ③应急预案"
        items = rule_extract_sub_items(text, parent_req_id=1)
        assert len(items) == 3
        assert all(it.parent_req_id == 1 for it in items)
        assert all(it.extraction_method == "rule" for it in items)

    def test_parenthesized_numbers(self):
        """(1)(2)(3) 编号子项拆解"""
        text = "服务方案（15分）：(1)配送时效保障措施 (2)客户投诉处理流程 (3)食品安全管控"
        items = rule_extract_sub_items(text, parent_req_id=2)
        assert len(items) == 3

    def test_grade_pattern(self):
        """评分档次模式: 优(10分) 良(8分)"""
        text = "企业业绩（10分）：优秀(10分) 良好(8分) 一般(5分)"
        items = rule_extract_sub_items(text, parent_req_id=3)
        assert len(items) >= 1
        assert items[0].max_score == 10.0
        assert "评分档次" in items[0].scoring_criteria

    def test_single_item_with_score(self):
        """无子项但有分值 → 整体作为单条"""
        text = "企业资质证书齐全度（满分5分）"
        items = rule_extract_sub_items(text, parent_req_id=4)
        assert len(items) == 1
        assert items[0].max_score == 5.0

    def test_no_score_no_items(self):
        """无分值无子项 → 空"""
        items = rule_extract_sub_items("请提供详细方案", parent_req_id=5)
        assert items == []

    def test_score_distribution(self):
        """子项分值之和合理"""
        text = "配送方案（满分30分）：①车辆配备(10分) ②温控方案(10分) ③路线规划(10分)"
        items = rule_extract_sub_items(text, parent_req_id=6)
        total = sum(it.max_score for it in items)
        assert total == 30.0


# ═══════════════════════════════════════════════════════════
# 优先级分类
# ═══════════════════════════════════════════════════════════

class TestClassifyPriority:

    def test_high(self):
        assert _classify_priority(15) == "high"
        assert _classify_priority(20) == "high"

    def test_medium(self):
        assert _classify_priority(8) == "medium"
        assert _classify_priority(14) == "medium"

    def test_low(self):
        assert _classify_priority(5) == "low"
        assert _classify_priority(0) == "low"


# ═══════════════════════════════════════════════════════════
# LLM 层提取（Mock）
# ═══════════════════════════════════════════════════════════

class TestLLMExtract:

    @pytest.mark.asyncio
    async def test_llm_returns_sub_items(self):
        """LLM 返回有效 JSON → 解析为子项"""
        mock_json = '[{"name":"冷链覆盖","max_score":10,"criteria":"全程控温","suggestion":"详述温控方案"}]'

        with patch(
            "app.services.scoring_extractor.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_json,
        ):
            items = await llm_extract_sub_items("复杂评分标准", parent_req_id=1, total_score=10)
            assert len(items) == 1
            assert items[0].sub_item_name == "冷链覆盖"
            assert items[0].max_score == 10.0
            assert items[0].extraction_method == "llm"

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self):
        """LLM 失败 → 空列表"""
        with patch(
            "app.services.scoring_extractor.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
            side_effect=RuntimeError("全部失败"),
        ):
            items = await llm_extract_sub_items("xxx", parent_req_id=1, total_score=10)
            assert items == []

    @pytest.mark.asyncio
    async def test_llm_invalid_json_returns_empty(self):
        """LLM 返回非法 JSON → 空列表"""
        with patch(
            "app.services.scoring_extractor.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
            return_value="这不是JSON",
        ):
            items = await llm_extract_sub_items("xxx", parent_req_id=1, total_score=10)
            assert items == []

    @pytest.mark.asyncio
    async def test_llm_markdown_wrapped(self):
        """LLM 返回 markdown 包裹的 JSON → 正确解析"""
        mock_resp = '```json\n[{"name":"子项A","max_score":5,"criteria":"标准A","suggestion":"建议A"}]\n```'

        with patch(
            "app.services.scoring_extractor.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            items = await llm_extract_sub_items("xxx", parent_req_id=1, total_score=5)
            assert len(items) == 1
            assert items[0].sub_item_name == "子项A"


# ═══════════════════════════════════════════════════════════
# 完整提取流程（Mock DB + LLM）
# ═══════════════════════════════════════════════════════════

class FakeRequirement:
    def __init__(self, id, content, max_score=None):
        self.id = id
        self.content = content
        self.category = "scoring"
        self.max_score = max_score


class TestScoringExtractor:

    @pytest.mark.asyncio
    async def test_no_requirements_empty_matrix(self):
        """无评分要求 → 空矩阵"""
        session = AsyncMock()
        extractor = ScoringExtractor(session)
        extractor._load_scoring_requirements = AsyncMock(return_value=[])

        matrix = await extractor.extract(1, 1)
        assert matrix.total_score == 0
        assert len(matrix.items) == 0

    @pytest.mark.asyncio
    async def test_rule_extraction_flow(self):
        """规则可拆解 → 不调 LLM"""
        reqs = [
            FakeRequirement(1, "配送方案（满分20分）：①冷链方案 ②应急预案", max_score=20),
        ]

        session = AsyncMock()
        extractor = ScoringExtractor(session)
        extractor._load_scoring_requirements = AsyncMock(return_value=reqs)

        with patch(
            "app.services.scoring_extractor.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
        ) as mock_llm:
            matrix = await extractor.extract(1, 1)
            # 规则已拆出子项，不应调 LLM
            mock_llm.assert_not_called()
            assert len(matrix.items) == 2
            assert matrix.extraction_method == "rule"

    @pytest.mark.asyncio
    async def test_llm_fallback_when_rule_fails(self):
        """规则无法拆解 → 走 LLM"""
        reqs = [
            FakeRequirement(1, "根据企业综合服务能力进行评定", max_score=15),
        ]
        mock_json = '[{"name":"服务能力","max_score":15,"criteria":"综合评定","suggestion":"详述服务案例"}]'

        session = AsyncMock()
        extractor = ScoringExtractor(session)
        extractor._load_scoring_requirements = AsyncMock(return_value=reqs)

        with patch(
            "app.services.scoring_extractor.LLMSelector.call_with_fallback",
            new_callable=AsyncMock,
            return_value=mock_json,
        ):
            matrix = await extractor.extract(1, 1)
            assert len(matrix.items) == 1
            assert matrix.items[0].extraction_method == "llm"
            assert matrix.extraction_method == "hybrid"

    @pytest.mark.asyncio
    async def test_total_score_aggregation(self):
        """子项分值之和 = total_score"""
        reqs = [
            FakeRequirement(1, "技术方案（10分）：①冷链(5分) ②温控(5分)", max_score=10),
            FakeRequirement(2, "企业资质（满分5分）", max_score=5),
        ]

        session = AsyncMock()
        extractor = ScoringExtractor(session)
        extractor._load_scoring_requirements = AsyncMock(return_value=reqs)

        matrix = await extractor.extract(1, 1)
        assert matrix.total_score == sum(it.max_score for it in matrix.items)

    @pytest.mark.asyncio
    async def test_response_suggestion_filled(self):
        """所有子项都有响应建议"""
        reqs = [
            FakeRequirement(1, "冷链配送覆盖（满分8分）", max_score=8),
        ]

        session = AsyncMock()
        extractor = ScoringExtractor(session)
        extractor._load_scoring_requirements = AsyncMock(return_value=reqs)

        matrix = await extractor.extract(1, 1)
        for item in matrix.items:
            assert item.response_suggestion, f"子项 '{item.sub_item_name}' 缺少响应建议"
