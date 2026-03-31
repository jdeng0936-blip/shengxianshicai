"""
全链路 E2E 测试 — 模拟完整投标流程

流程: 创建项目 → 添加要求 → 初始化章节 → 合规检查 → 风险报告 → 导出检查
（跳过真实 LLM 调用的步骤: AI 解析/生成/重写需要 API Key）
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestFullBidFlow:
    """完整投标流程 E2E 测试"""

    async def test_01_create_project(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 1: 创建投标项目"""
        resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
            "project_name": "E2E测试-XX市第一中学2026年食材配送",
            "tender_org": "XX市第一中学",
            "customer_type": "school",
            "tender_type": "open",
            "budget_amount": 800000,
            "delivery_scope": "校本部食堂，日配送约500人份",
            "delivery_period": "一年",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "draft"
        assert data["customer_type"] == "school"
        self.__class__.project_id = data["id"]

    async def test_02_add_requirements(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 2: 手动添加招标要求（模拟解析结果）"""
        pid = self.__class__.project_id
        reqs = [
            {"category": "disqualification", "content": "投标人须持有有效食品经营许可证", "is_mandatory": True},
            {"category": "disqualification", "content": "投标人须拥有不少于3辆冷藏运输车辆", "is_mandatory": True},
            {"category": "qualification", "content": "投标人须通过HACCP或ISO22000体系认证", "is_mandatory": True},
            {"category": "scoring", "content": "冷链配送方案及温控措施", "max_score": 20, "is_mandatory": False},
            {"category": "scoring", "content": "食品安全管理体系及检测能力", "max_score": 15, "is_mandatory": False},
            {"category": "scoring", "content": "人员配置及培训方案", "max_score": 10, "is_mandatory": False},
            {"category": "technical", "content": "配送时间须在每日6:00前完成", "is_mandatory": True},
            {"category": "commercial", "content": "报价采用下浮率方式", "is_mandatory": True},
        ]
        resp = await async_client.post(
            f"/api/v1/bid-projects/{pid}/requirements/batch",
            headers=auth_headers,
            json=reqs,
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 8

    async def test_03_init_chapters(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 3: 初始化 9 章结构"""
        pid = self.__class__.project_id
        resp = await async_client.post(
            f"/api/v1/bid-projects/{pid}/init-chapters",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        chapters = resp.json()["data"]
        assert len(chapters) == 9
        assert chapters[0]["chapter_no"] == "第一章"
        assert chapters[0]["status"] == "draft"

    async def test_04_compliance_check(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 4: 合规检查（无企业数据，应报风险）"""
        pid = self.__class__.project_id
        resp = await async_client.post(
            f"/api/v1/bid-projects/{pid}/compliance-check",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 8
        # 没有企业信息，废标项应该 failed
        assert data["failed"] > 0

    async def test_05_risk_report(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 5: 风险报告（应包含致命风险：无企业、章节空）"""
        pid = self.__class__.project_id
        resp = await async_client.post(
            f"/api/v1/bid-projects/{pid}/risk-report",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        report = resp.json()["data"]
        assert report["summary"]["total"] > 0
        assert report["summary"]["fatal"] > 0  # 未关联企业 → fatal
        assert report["summary"]["can_submit"] is False

    async def test_06_export_check(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 6: 导出前检查（有致命项应阻止）"""
        pid = self.__class__.project_id
        resp = await async_client.get(
            f"/api/v1/bid-projects/{pid}/export-check",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["can_export"] is False
        assert data["fatal_count"] > 0
        assert "disclaimer" in data

    async def test_07_init_quotation(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 7: 初始化报价单"""
        pid = self.__class__.project_id
        resp = await async_client.post(
            f"/api/v1/bid-projects/{pid}/init-quotation?discount_rate=0.08",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        sheet = resp.json()["data"]
        assert sheet["discount_rate"] == 0.08
        assert len(sheet["items"]) > 0

    async def test_08_create_enterprise_and_link(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 8: 创建企业并关联"""
        # 创建企业
        resp = await async_client.post("/api/v1/enterprises", headers=auth_headers, json={
            "name": "E2E测试食品公司",
            "credit_code": "91110000MA01234567",
            "legal_representative": "张三",
            "food_license_no": "JY11234567890123",
            "cold_chain_vehicles": 5,
            "contact_person": "李四",
            "contact_phone": "13800138000",
        })
        assert resp.status_code == 200
        ent_id = resp.json()["data"]["id"]

        # 关联到项目
        pid = self.__class__.project_id
        resp = await async_client.put(
            f"/api/v1/bid-projects/{pid}",
            headers=auth_headers,
            json={"enterprise_id": ent_id},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["enterprise_id"] == ent_id
        self.__class__.enterprise_id = ent_id

    async def test_09_readiness_check(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 9: 企业完整度检查"""
        ent_id = self.__class__.enterprise_id
        resp = await async_client.get(
            f"/api/v1/enterprises/{ent_id}/readiness",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "score" in data
        assert data["score"] > 0
        assert "missing" in data

    async def test_10_risk_report_after_enterprise(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 10: 关联企业后再跑风险报告（致命项应减少）"""
        pid = self.__class__.project_id
        resp = await async_client.post(
            f"/api/v1/bid-projects/{pid}/risk-report",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        report = resp.json()["data"]
        # 已有企业信息，"未关联企业"的 fatal 应消失
        fatal_titles = [r["title"] for r in report["risks"] if r["level"] == "fatal"]
        assert not any("未关联" in t for t in fatal_titles)

    async def test_11_project_detail_complete(self, async_client: AsyncClient, auth_headers: dict):
        """步骤 11: 最终项目详情验证"""
        pid = self.__class__.project_id
        resp = await async_client.get(f"/api/v1/bid-projects/{pid}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["requirements"]) == 8
        assert len(data["chapters"]) == 9
        assert data["enterprise_id"] is not None

    async def test_12_cleanup(self, async_client: AsyncClient, auth_headers: dict):
        """清理: 删除测试数据"""
        pid = self.__class__.project_id
        ent_id = self.__class__.enterprise_id
        await async_client.delete(f"/api/v1/bid-projects/{pid}", headers=auth_headers)
        await async_client.delete(f"/api/v1/enterprises/{ent_id}", headers=auth_headers)
