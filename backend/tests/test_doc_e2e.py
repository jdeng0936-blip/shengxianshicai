"""
端到端联调测试 — 创建项目 → 添加要求 → 初始化章节 → 合规检查 → 配额检查 → 废标提取

全部使用 Mock，严禁真实 LLM / OSS 调用。
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestDocE2E:
    """投标文件全链路 E2E 测试"""

    async def test_01_create_project(self, async_client: AsyncClient, auth_headers: dict):
        """创建投标项目"""
        resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
            "project_name": "E2E联调-XX学校2026年食材配送",
            "tender_org": "XX市第二中学",
            "customer_type": "school",
            "tender_type": "open",
            "budget_amount": 500000,
            "delivery_scope": "校本部食堂",
            "delivery_period": "一年",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "draft"
        self.__class__.project_id = data["id"]

    async def test_02_add_requirements(self, async_client: AsyncClient, auth_headers: dict):
        """批量添加招标要求"""
        pid = self.__class__.project_id
        reqs = [
            {"category": "disqualification", "content": "投标人须持有有效食品经营许可证", "is_mandatory": True},
            {"category": "disqualification", "content": "投标人须拥有不少于3辆冷链车辆", "is_mandatory": True},
            {"category": "qualification", "content": "通过HACCP或ISO22000认证", "is_mandatory": True},
            {"category": "scoring", "content": "冷链配送方案", "max_score": 20, "is_mandatory": False},
            {"category": "scoring", "content": "食品安全管理体系", "max_score": 15, "is_mandatory": False},
            {"category": "technical", "content": "每日6:00前完成配送", "is_mandatory": True},
            {"category": "commercial", "content": "报价采用下浮率方式", "is_mandatory": True},
        ]
        resp = await async_client.post(
            f"/api/v1/bid-projects/{pid}/requirements/batch",
            headers=auth_headers, json=reqs,
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 7

    async def test_03_init_chapters(self, async_client: AsyncClient, auth_headers: dict):
        """初始化 9 章结构"""
        pid = self.__class__.project_id
        resp = await async_client.post(
            f"/api/v1/bid-projects/{pid}/init-chapters",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        chapters = resp.json()["data"]
        assert len(chapters) == 9
        assert chapters[0]["chapter_no"] == "第一章"

    async def test_04_compliance_check(self, async_client: AsyncClient, auth_headers: dict):
        """合规检查（无企业数据，应报风险）"""
        pid = self.__class__.project_id
        resp = await async_client.post(
            f"/api/v1/bid-projects/{pid}/compliance-check",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] > 0
        assert data["failed"] > 0

    async def test_05_subscription_check(self, async_client: AsyncClient, auth_headers: dict):
        """订阅配额检查"""
        resp = await async_client.get(
            "/api/v1/subscriptions/current",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "plan_type" in data
        assert "remaining_quota" in data
        assert "is_active" in data

    async def test_06_create_payment_order(self, async_client: AsyncClient, auth_headers: dict):
        """创建支付订单"""
        resp = await async_client.post(
            "/api/v1/payments/create-order",
            headers=auth_headers,
            json={"order_type": "per_document", "payment_method": "manual"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["amount"] == 199
        assert data["status"] == "pending"
        assert data["order_no"].startswith("FBP-")

    async def test_07_project_data_integrity(self, async_client: AsyncClient, auth_headers: dict):
        """验证项目数据完整性"""
        pid = self.__class__.project_id
        resp = await async_client.get(
            f"/api/v1/bid-projects/{pid}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["chapters"]) == 9
        assert len(data["requirements"]) == 7

    async def test_08_disqualification_keyword_extraction(self):
        """废标关键词提取引擎验证"""
        from app.services.tender_parser import _extract_disqualification_items

        sample_text = (
            "投标人须持有有效的食品经营许可证，未取得者将按废标处理。"
            "投标文件未按规定密封的，不予受理。"
            "如果投标人存在串通投标行为，则取消投标资格。"
            "冷链配送方案需详细描述温控措施。"
        )
        items = _extract_disqualification_items(sample_text)
        assert len(items) >= 3
        contents = [i["content"] for i in items]
        assert any("食品经营许可" in c for c in contents)
        assert any("密封" in c for c in contents)
        assert any("串通投标" in c for c in contents)

    async def test_09_quotation_chapter_intercept(self):
        """报价章节拦截验证"""
        from app.services.bid_chapter_engine import is_quotation_chapter, get_quotation_template

        assert is_quotation_chapter("第八章", "报价文件") is True
        assert is_quotation_chapter("第三章", "食材采购") is False
        tpl = get_quotation_template()
        assert "报价引擎" in tpl

    async def test_10_replace_high_risk_fields(self):
        """高风险字段替换验证"""
        from app.services.bid_generation_service import replace_high_risk_fields
        from unittest.mock import MagicMock

        # 无企业数据 → 保留提示
        result = replace_high_risk_fields("我公司拥有{{冷链车辆数}}冷链车辆", None, None)
        assert "【请填写" in result

        # 有企业数据 → 替换为真实值
        ent = MagicMock()
        ent.name = "测试食品有限公司"
        ent.cold_chain_vehicles = 8
        ent.normal_vehicles = None
        ent.warehouse_area = None
        ent.cold_storage_area = None
        ent.employee_count = None
        ent.registered_capital = None
        ent.service_customers = None
        ent.credit_code = None

        result = replace_high_risk_fields("{{企业名称}}拥有{{冷链车辆数}}", ent, None)
        assert "测试食品有限公司" in result
        assert "8辆" in result
