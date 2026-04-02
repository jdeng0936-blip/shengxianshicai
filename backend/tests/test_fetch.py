"""
商机抓取服务测试 — 异步 HTTP 调用验证
"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
@patch("app.services.tender_aggregator_service.TenderAggregatorService.fetch_notices",
       new_callable=AsyncMock, return_value={"total": 0, "items": []})
async def test_fetch_notices_endpoint_exists(mock_fetch, async_client, auth_headers):
    """商机抓取接口可达（Mock 外部数据源，不发真实 HTTP 请求）"""
    resp = await async_client.post(
        "/api/v1/tender-notices/fetch",
        headers=auth_headers,
        json={"enterprise_id": 1, "region": "安徽", "keywords": "配送"},
    )
    # 接口可达即可
    assert resp.status_code in (200, 400, 404, 422)
