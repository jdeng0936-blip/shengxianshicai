"""
一键投标体检聚合服务测试 — 全量 Mock 子服务

严禁调用真实 DB/LLM。所有子检查服务都 mock 返回值。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Optional, List

from app.services.bid_checkup_service import (
    BidCheckupService,
    BidCheckupReport,
    CheckupDimension,
)


# ── Mock 对象 ────────────────────────────────────────

class FakeProject:
    def __init__(self, id=1, tenant_id=1, enterprise_id=10,
                 project_name="测试项目", deadline="2026-08-01", chapters=None):
        self.id = id
        self.tenant_id = tenant_id
        self.enterprise_id = enterprise_id
        self.project_name = project_name
        self.deadline = deadline
        self.chapters = chapters or []


class FakeChapter:
    def __init__(self, chapter_no, title, content):
        self.chapter_no = chapter_no
        self.title = title
        self.content = content


# ═══════════════════════════════════════════════════════════
# 核心聚合逻辑测试
# ═══════════════════════════════════════════════════════════

class TestBidCheckupService:

    @pytest.mark.asyncio
    async def test_project_not_found_raises(self):
        """项目不存在 → ValueError"""
        session = AsyncMock()
        svc = BidCheckupService(session)
        svc._load_project = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="项目不存在"):
            await svc.run_checkup(999, 1)

    @pytest.mark.asyncio
    async def test_all_passed_scenario(self):
        """全部维度通过 → overall_status=passed, can_submit=True"""
        session = AsyncMock()
        svc = BidCheckupService(session)
        svc._load_project = AsyncMock(return_value=FakeProject())
        svc._check_credentials = AsyncMock(return_value=CheckupDimension(
            name="资质有效期", score=100, status="passed", summary="全部资质有效"
        ))
        svc._check_compliance = AsyncMock(return_value=CheckupDimension(
            name="合规检查", score=95, status="passed", summary="合规"
        ))
        svc._check_risk_report = AsyncMock(return_value=CheckupDimension(
            name="风险报告", score=100, status="passed", summary="无风险"
        ))
        svc._check_scoring_coverage = AsyncMock(return_value=CheckupDimension(
            name="评分覆盖", score=90, status="passed", summary="已响应"
        ))
        svc._check_consistency = AsyncMock(return_value=CheckupDimension(
            name="数据一致性", score=100, status="passed", summary="一致"
        ))

        report = await svc.run_checkup(1, 1)
        assert report.overall_status == "passed"
        assert report.can_submit is True
        assert report.fatal_count == 0
        assert report.warning_count == 0
        assert report.overall_score == 97  # (100+95+100+90+100)/5 = 97
        assert len(report.dimensions) == 5

    @pytest.mark.asyncio
    async def test_fatal_blocks_submit(self):
        """有 failed 维度 → can_submit=False, overall_status=failed"""
        session = AsyncMock()
        svc = BidCheckupService(session)
        svc._load_project = AsyncMock(return_value=FakeProject())
        svc._check_credentials = AsyncMock(return_value=CheckupDimension(
            name="资质有效期", score=0, status="failed",
            summary="2 个过期", issue_count=2,
        ))
        svc._check_compliance = AsyncMock(return_value=CheckupDimension(
            name="合规检查", score=100, status="passed", summary="OK"
        ))
        svc._check_risk_report = AsyncMock(return_value=CheckupDimension(
            name="风险报告", score=100, status="passed", summary="OK"
        ))
        svc._check_scoring_coverage = AsyncMock(return_value=CheckupDimension(
            name="评分覆盖", score=100, status="passed", summary="OK"
        ))
        svc._check_consistency = AsyncMock(return_value=CheckupDimension(
            name="数据一致性", score=100, status="passed", summary="OK"
        ))

        report = await svc.run_checkup(1, 1)
        assert report.overall_status == "failed"
        assert report.can_submit is False
        assert report.fatal_count == 2

    @pytest.mark.asyncio
    async def test_warning_not_blocks_submit(self):
        """只有 warning → can_submit=True, overall_status=warning"""
        session = AsyncMock()
        svc = BidCheckupService(session)
        svc._load_project = AsyncMock(return_value=FakeProject())
        svc._check_credentials = AsyncMock(return_value=CheckupDimension(
            name="资质有效期", score=70, status="warning",
            summary="3 个即将过期", issue_count=3,
        ))
        svc._check_compliance = AsyncMock(return_value=CheckupDimension(
            name="合规检查", score=100, status="passed", summary="OK"
        ))
        svc._check_risk_report = AsyncMock(return_value=CheckupDimension(
            name="风险报告", score=100, status="passed", summary="OK"
        ))
        svc._check_scoring_coverage = AsyncMock(return_value=CheckupDimension(
            name="评分覆盖", score=100, status="passed", summary="OK"
        ))
        svc._check_consistency = AsyncMock(return_value=CheckupDimension(
            name="数据一致性", score=100, status="passed", summary="OK"
        ))

        report = await svc.run_checkup(1, 1)
        assert report.overall_status == "warning"
        assert report.can_submit is True
        assert report.warning_count == 3

    @pytest.mark.asyncio
    async def test_error_dimension_not_counted(self):
        """某维度 error → 不参与均分计算，不阻塞流程"""
        session = AsyncMock()
        svc = BidCheckupService(session)
        svc._load_project = AsyncMock(return_value=FakeProject())
        svc._check_credentials = AsyncMock(return_value=CheckupDimension(
            name="资质有效期", score=50, status="error", summary="服务异常"
        ))
        svc._check_compliance = AsyncMock(return_value=CheckupDimension(
            name="合规检查", score=100, status="passed", summary="OK"
        ))
        svc._check_risk_report = AsyncMock(return_value=CheckupDimension(
            name="风险报告", score=80, status="passed", summary="OK"
        ))
        svc._check_scoring_coverage = AsyncMock(return_value=CheckupDimension(
            name="评分覆盖", score=90, status="passed", summary="OK"
        ))
        svc._check_consistency = AsyncMock(return_value=CheckupDimension(
            name="数据一致性", score=100, status="passed", summary="OK"
        ))

        report = await svc.run_checkup(1, 1)
        # error 维度不计入均分: (100+80+90+100)/4 = 92.5 → 92
        assert report.overall_score == 92
        assert report.can_submit is True

    @pytest.mark.asyncio
    async def test_no_enterprise_credential_warning(self):
        """项目未关联企业 → 资质维度 warning"""
        session = AsyncMock()
        svc = BidCheckupService(session)
        project = FakeProject(enterprise_id=None)

        dim = await svc._check_credentials(project, 1)
        assert dim.status == "warning"
        assert dim.score == 50
        assert "未关联企业" in dim.summary

    @pytest.mark.asyncio
    async def test_credential_service_failure_degrades(self):
        """CredentialAlertService 异常 → error 状态不抛出"""
        session = AsyncMock()
        svc = BidCheckupService(session)
        project = FakeProject()

        with patch(
            "app.services.credential_alert_service.CredentialAlertService"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.check_bid_readiness = AsyncMock(
                side_effect=RuntimeError("DB connection lost")
            )
            mock_cls.return_value = mock_instance

            dim = await svc._check_credentials(project, 1)
            assert dim.status == "error"
            assert dim.score == 50

    @pytest.mark.asyncio
    async def test_report_dict_serialization(self):
        """报告可正确序列化为 dict"""
        report = BidCheckupReport(project_id=1, project_name="测试")
        report.dimensions = [
            CheckupDimension(name="资质有效期", score=100, status="passed", summary="OK"),
        ]
        d = report.to_dict()
        assert d["project_id"] == 1
        assert d["project_name"] == "测试"
        assert len(d["dimensions"]) == 1
        assert d["dimensions"][0]["name"] == "资质有效期"
