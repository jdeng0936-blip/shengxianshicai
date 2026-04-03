"""
企业能力画像测试 — 五维度评分逻辑（全量 Mock DB）

严禁连接真实数据库。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.capability_profile import (
    CapabilityProfileService,
    DimensionScore,
    _CORE_CREDENTIALS,
)


# ── Mock 对象 ────────────────────────────────────────

class FakeEnterprise:
    def __init__(self, **kwargs):
        defaults = {
            "id": 1, "tenant_id": 1, "name": "测试食品公司",
            "cold_chain_vehicles": 8, "normal_vehicles": 5,
            "warehouse_area": 3000.0, "cold_storage_area": 800.0,
            "cold_storage_temp": "-18℃~4℃",
            "haccp_certified": True, "iso22000_certified": True,
            "service_customers": 30, "employee_count": 100,
            "established_date": "2018-06-01", "annual_revenue": "2000",
            "sc_certified": False, "food_license_no": "JY001",
            "food_license_expiry": "2027-12-31",
            "legal_representative": "张三", "registered_capital": "500",
            "credit_code": "91110000MA001", "short_name": "测试",
            "business_scope": "食品配送", "address": "北京",
            "contact_person": "李四", "contact_phone": "13800138000",
            "contact_email": "test@test.com", "description": "",
            "competitive_advantages": "", "established_date": "2018-06-01",
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)
        self.credentials = []
        self.images = []


class FakeCredential:
    def __init__(self, cred_type, expiry_date=None, is_permanent=False):
        self.cred_type = cred_type
        self.cred_name = cred_type
        self.cred_no = f"{cred_type}_001"
        self.expiry_date = expiry_date
        self.is_permanent = is_permanent
        self.enterprise_id = 1
        self.tenant_id = 1


# ═══════════════════════════════════════════════════════════
# 维度1: 硬件能力
# ═══════════════════════════════════════════════════════════

class TestHardwareScore:

    @pytest.mark.asyncio
    async def test_full_hardware(self):
        """满配硬件 → 高分"""
        svc = CapabilityProfileService(session=AsyncMock())
        ent = FakeEnterprise(
            cold_chain_vehicles=15, warehouse_area=6000,
            cold_storage_area=3000, cold_storage_temp="-18℃~4℃",
        )
        d = await svc._score_hardware(ent)
        assert d.name == "硬件能力"
        assert d.score >= 80

    @pytest.mark.asyncio
    async def test_zero_hardware(self):
        """无硬件 → 低分"""
        svc = CapabilityProfileService(session=AsyncMock())
        ent = FakeEnterprise(
            cold_chain_vehicles=0, normal_vehicles=0,
            warehouse_area=0, cold_storage_area=0, cold_storage_temp=None,
        )
        d = await svc._score_hardware(ent)
        assert d.score == 0


# ═══════════════════════════════════════════════════════════
# 维度2: 合规能力
# ═══════════════════════════════════════════════════════════

class TestComplianceScore:

    @pytest.mark.asyncio
    async def test_full_credentials(self):
        """五大核心资质齐全 + 无过期 → 高分"""
        creds = [
            FakeCredential("food_license", "2027-12-31"),
            FakeCredential("business_license", is_permanent=True),
            FakeCredential("haccp", "2027-06-30"),
            FakeCredential("iso22000", "2027-06-30"),
            FakeCredential("sc", "2027-06-30"),
        ]
        session = AsyncMock()
        # mock 资质查询
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = creds
        session.execute = AsyncMock(return_value=mock_result)

        svc = CapabilityProfileService(session=session)
        ent = FakeEnterprise(haccp_certified=True, iso22000_certified=True)
        d = await svc._score_compliance(1, 1, ent)
        assert d.score >= 80

    @pytest.mark.asyncio
    async def test_no_credentials(self):
        """无资质 → 低分"""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        svc = CapabilityProfileService(session=session)
        ent = FakeEnterprise(haccp_certified=False, iso22000_certified=False)
        d = await svc._score_compliance(1, 1, ent)
        assert d.score < 20


# ═══════════════════════════════════════════════════════════
# 维度3: 服务能力
# ═══════════════════════════════════════════════════════════

class TestServiceScore:

    def test_strong_service(self):
        """强服务能力 → 高分"""
        svc = CapabilityProfileService(session=AsyncMock())
        ent = FakeEnterprise(
            service_customers=60, employee_count=250,
            established_date="2012-01-01", annual_revenue="6000",
        )
        d = svc._score_service(ent)
        assert d.score >= 80

    def test_new_company(self):
        """新公司无数据 → 低分"""
        svc = CapabilityProfileService(session=AsyncMock())
        ent = FakeEnterprise(
            service_customers=0, employee_count=0,
            established_date=None, annual_revenue=None,
        )
        d = svc._score_service(ent)
        assert d.score == 0


# ═══════════════════════════════════════════════════════════
# 维度4: 文档能力
# ═══════════════════════════════════════════════════════════

class TestDocumentationScore:

    @pytest.mark.asyncio
    async def test_no_projects(self):
        """无项目 → 基线 50 分"""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        svc = CapabilityProfileService(session=session)
        d = await svc._score_documentation(1, 1)
        assert d.score == 50

    @pytest.mark.asyncio
    async def test_high_accept_rate(self):
        """高接受率 → 高分"""
        session = AsyncMock()
        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            m = MagicMock()
            if call_count[0] == 1:
                # 项目 ID 列表
                m.fetchall.return_value = [(1,), (2,)]
                return m
            else:
                # 反馈统计: accept=8, edit=2, reject=0
                m.fetchall.return_value = [
                    ("accept", 8, None),
                    ("edit", 2, 0.05),
                ]
                return m

        session.execute = mock_execute
        svc = CapabilityProfileService(session=session)
        d = await svc._score_documentation(1, 1)
        assert d.score >= 70


# ═══════════════════════════════════════════════════════════
# 维度5: 竞争能力
# ═══════════════════════════════════════════════════════════

class TestCompetitivenessScore:

    @pytest.mark.asyncio
    async def test_experienced_enterprise(self):
        """多项目+高完成率+有中标 → 高分"""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("completed", 10),
            ("submitted", 5),
            ("won", 4),
            ("draft", 3),
        ]
        session.execute = AsyncMock(return_value=mock_result)

        svc = CapabilityProfileService(session=session)
        d = await svc._score_competitiveness(1, 1)
        assert d.score >= 50
        assert d.details["total_projects"] == 22

    @pytest.mark.asyncio
    async def test_no_projects(self):
        """无项目 → 0 分"""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        svc = CapabilityProfileService(session=session)
        d = await svc._score_competitiveness(1, 1)
        assert d.score == 0


# ═══════════════════════════════════════════════════════════
# 完整画像构建
# ═══════════════════════════════════════════════════════════

class TestBuildProfile:

    @pytest.mark.asyncio
    async def test_profile_has_five_dimensions(self):
        """画像包含五个维度"""
        svc = CapabilityProfileService(session=AsyncMock())

        ent = FakeEnterprise()
        svc._load_enterprise = AsyncMock(return_value=ent)
        svc._score_hardware = AsyncMock(return_value=DimensionScore("硬件能力", 70))
        svc._score_compliance = AsyncMock(return_value=DimensionScore("合规能力", 80))
        svc._score_service = MagicMock(return_value=DimensionScore("服务能力", 60))
        svc._score_documentation = AsyncMock(return_value=DimensionScore("文档能力", 50))
        svc._score_competitiveness = AsyncMock(return_value=DimensionScore("竞争能力", 40))

        profile = await svc.build_profile(1, 1)
        assert len(profile.dimensions) == 5
        assert profile.overall_score == 60  # (70+80+60+50+40)/5

    @pytest.mark.asyncio
    async def test_profile_enterprise_not_found(self):
        """企业不存在 → ValueError"""
        svc = CapabilityProfileService(session=AsyncMock())
        svc._load_enterprise = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="企业不存在"):
            await svc.build_profile(999, 1)

    @pytest.mark.asyncio
    async def test_overall_score_range(self):
        """总分在 0~100 范围内"""
        svc = CapabilityProfileService(session=AsyncMock())

        ent = FakeEnterprise()
        svc._load_enterprise = AsyncMock(return_value=ent)
        svc._score_hardware = AsyncMock(return_value=DimensionScore("硬件能力", 100))
        svc._score_compliance = AsyncMock(return_value=DimensionScore("合规能力", 100))
        svc._score_service = MagicMock(return_value=DimensionScore("服务能力", 100))
        svc._score_documentation = AsyncMock(return_value=DimensionScore("文档能力", 100))
        svc._score_competitiveness = AsyncMock(return_value=DimensionScore("竞争能力", 100))

        profile = await svc.build_profile(1, 1)
        assert 0 <= profile.overall_score <= 100
