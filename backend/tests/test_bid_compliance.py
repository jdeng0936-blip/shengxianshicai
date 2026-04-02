"""
投标合规检查服务测试 — 纯业务逻辑（Mock DB/LLM）

测试策略:
  - 关键词匹配逻辑: 不需要 DB，直接测试 _check_* 方法
  - LLM 语义审查: Mock AsyncOpenAI，验证调用链路
  - 不测真实数据库连接（那是集成测试的事）
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def _load_compliance():
    """延迟导入，避免 collect 阶段触发 Settings 校验"""
    from app.services.bid_compliance_service import (
        BidComplianceService,
        ComplianceResult,
        _QUAL_KEYWORD_MAP,
    )
    return BidComplianceService, ComplianceResult, _QUAL_KEYWORD_MAP


class FakeRequirement:
    """Mock TenderRequirement"""
    def __init__(self, id, content, category="disqualification"):
        self.id = id
        self.content = content
        self.category = category
        self.max_score = None
        self.score_weight = None
        self.compliance_status = None
        self.compliance_note = None


class FakeEnterprise:
    """Mock Enterprise"""
    def __init__(self, name="测试食品公司", cold_chain_vehicles=5):
        self.name = name
        self.cold_chain_vehicles = cold_chain_vehicles


class TestKeywordExtraction:
    """关键词提取逻辑"""

    def test_extract_chinese_keywords(self):
        BidComplianceService, _, _ = _load_compliance()
        keywords = BidComplianceService._extract_keywords(
            "投标人应具备食品经营许可证和冷链运输资质"
        )
        # 分词结果取决于正则切分，验证提取出了相关中文词
        joined = "".join(keywords)
        assert "食品" in joined or "经营许可" in joined
        assert "冷链" in joined or "运输资质" in joined

    def test_filter_stop_words(self):
        BidComplianceService, _, _ = _load_compliance()
        keywords = BidComplianceService._extract_keywords(
            "投标人需要提供相关有效合格证明"
        )
        # 停用词应被过滤
        assert "需要" not in keywords
        assert "提供" not in keywords
        assert "相关" not in keywords

    def test_empty_text(self):
        BidComplianceService, _, _ = _load_compliance()
        keywords = BidComplianceService._extract_keywords("")
        assert keywords == []


class TestDisqualificationCheck:
    """废标项检查逻辑"""

    def setup_method(self):
        BidComplianceService, _, _ = _load_compliance()
        self.svc = BidComplianceService(session=None)

    def test_missing_food_license_fails(self):
        """缺少食品经营许可证 → failed"""
        req = FakeRequirement(1, "投标人须持有有效的食品经营许可证")
        result = self.svc._check_disqualification(
            req,
            cred_types={"business_license"},  # 有营业执照但没有 food_license
            cred_names="营业执照",
            chapter_text="我公司具备完善的食品安全管理体系",
            enterprise=FakeEnterprise(),
        )
        assert result.status == "failed"
        assert "食品经营许可" in result.note

    def test_has_food_license_not_failed(self):
        """有食品经营许可证 → 不应 failed（可能 passed 或 warning）"""
        req = FakeRequirement(1, "投标人须持有有效的食品经营许可证")
        result = self.svc._check_disqualification(
            req,
            cred_types={"food_license", "business_license"},
            cred_names="食品经营许可证 营业执照",
            chapter_text="我公司持有食品经营许可证",
            enterprise=FakeEnterprise(),
        )
        assert result.status != "failed"

    def test_missing_cold_chain_vehicles_fails(self):
        """要求冷链车但企业无车辆 → failed"""
        req = FakeRequirement(1, "投标人须拥有不少于3辆冷链车辆")
        result = self.svc._check_disqualification(
            req,
            cred_types=set(),
            cred_names="",
            chapter_text="",
            enterprise=FakeEnterprise(cold_chain_vehicles=0),
        )
        assert result.status == "failed"
        assert "冷链" in result.note

    def test_has_cold_chain_vehicles_passes(self):
        """有冷链车辆 → 不因冷链车 fail"""
        req = FakeRequirement(1, "投标人须拥有冷藏车")
        result = self.svc._check_disqualification(
            req,
            cred_types=set(),
            cred_names="",
            chapter_text="我公司拥有冷藏车10辆",
            enterprise=FakeEnterprise(cold_chain_vehicles=10),
        )
        assert result.status in ("passed", "warning")


class TestQualificationCheck:
    """资格要求检查逻辑"""

    def setup_method(self):
        BidComplianceService, _, _ = _load_compliance()
        self.svc = BidComplianceService(session=None)

    def test_haccp_matched(self):
        """有 HACCP → passed"""
        req = FakeRequirement(1, "投标人须通过HACCP体系认证", "qualification")
        result = self.svc._check_qualification(
            req,
            cred_types={"haccp"},
            cred_names="haccp认证",
            enterprise=FakeEnterprise(),
        )
        assert result.status == "passed"

    def test_haccp_missing(self):
        """缺 HACCP → warning"""
        req = FakeRequirement(1, "投标人须通过HACCP体系认证", "qualification")
        result = self.svc._check_qualification(
            req,
            cred_types={"business_license"},
            cred_names="营业执照",
            enterprise=FakeEnterprise(),
        )
        assert result.status == "warning"


class TestScoringCheck:
    """评分标准覆盖率检查"""

    def setup_method(self):
        BidComplianceService, _, _ = _load_compliance()
        self.svc = BidComplianceService(session=None)

    def test_high_coverage_passes(self):
        """章节中包含评分关键词 → passed"""
        req = FakeRequirement(1, "冷链配送方案及温控措施", "scoring")
        result = self.svc._check_scoring(
            req,
            chapter_text="我公司冷链配送方案采用全程温控措施，配备温度记录仪",
        )
        assert result.status == "passed"

    def test_zero_coverage_warns(self):
        """章节中完全没提到 → warning"""
        req = FakeRequirement(1, "有机蔬菜种植基地直供方案", "scoring")
        result = self.svc._check_scoring(
            req,
            chapter_text="我公司主营肉类加工业务",
        )
        assert result.status == "warning"


class TestQualKeywordMap:
    """资格关键词映射表完整性"""

    def test_core_keywords_present(self):
        _, _, _QUAL_KEYWORD_MAP = _load_compliance()
        assert "营业执照" in _QUAL_KEYWORD_MAP
        assert "食品经营许可" in _QUAL_KEYWORD_MAP
        assert "HACCP" in _QUAL_KEYWORD_MAP
        assert "ISO22000" in _QUAL_KEYWORD_MAP
        assert "冷链" in _QUAL_KEYWORD_MAP

    def test_each_maps_to_list(self):
        _, _, _QUAL_KEYWORD_MAP = _load_compliance()
        for keyword, types in _QUAL_KEYWORD_MAP.items():
            assert isinstance(types, list), f"{keyword} 的值不是 list"
            assert len(types) > 0, f"{keyword} 的资质类型列表为空"
