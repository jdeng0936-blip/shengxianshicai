"""
认证模块测试 — 登录 / 鉴权 / Token
"""
import pytest


@pytest.mark.asyncio
async def test_login_success(async_client):
    """正确凭据登录 → 200 + access_token"""
    resp = await async_client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert "access_token" in data["data"]


@pytest.mark.asyncio
async def test_login_wrong_password(async_client):
    """错误密码 → 401"""
    resp = await async_client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "wrong_password",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token(async_client):
    """无 Token 访问受保护路由 → 401/403"""
    resp = await async_client.get("/api/v1/projects")
    assert resp.status_code in (401, 403)
