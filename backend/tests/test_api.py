"""
API 集成测试 — 登录 / 企业列表 / 商机抓取
"""
import pytest


@pytest.mark.asyncio
async def test_login_returns_token(async_client):
    """登录接口返回 access_token"""
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data.get("data", {})


@pytest.mark.asyncio
async def test_get_enterprises_requires_auth(async_client):
    """未认证访问企业列表 → 401/403"""
    resp = await async_client.get("/api/v1/enterprises")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_enterprises_with_auth(async_client, auth_headers):
    """认证后可获取企业列表"""
    resp = await async_client.get("/api/v1/enterprises", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_fetch_tender_notices_requires_auth(async_client):
    """未认证抓取商机 → 401/403"""
    resp = await async_client.post(
        "/api/v1/tender-notices/fetch",
        json={"enterprise_id": 1, "region": "安徽", "keywords": "配送"},
    )
    assert resp.status_code in (401, 403)
