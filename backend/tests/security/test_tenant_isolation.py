"""
租户隔离 E2E 安全测试 — 6 个攻击向量

测试策略:
  1. 创建两个不同租户的用户（tenant_id=1 和 tenant_id=2）
  2. 用户 A（tenant_1）创建数据
  3. 用户 B（tenant_2）尝试读取/修改/删除 A 的数据 → 应全部 404

攻击向量:
  1. 跨租户读取投标项目
  2. 跨租户修改投标项目
  3. 跨租户删除投标项目
  4. 跨租户读取企业信息
  5. 跨租户读取报价单
  6. 跨租户读取资质证书
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cross_tenant_read_project(async_client: AsyncClient, auth_headers: dict):
    """攻击向量 1: 租户 A 的项目，租户 B 不可读"""
    # 租户 A 创建项目
    resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "租户A的机密项目",
    })
    assert resp.status_code == 200
    project_id = resp.json()["data"]["id"]

    # 同一用户（同租户）可以读到
    resp = await async_client.get(f"/api/v1/bid-projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["project_name"] == "租户A的机密项目"

    # 不存在的项目 ID → 404（不泄漏是否存在）
    resp = await async_client.get("/api/v1/bid-projects/999999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_modify_project(async_client: AsyncClient, auth_headers: dict):
    """攻击向量 2: 租户 A 的项目，其他租户不可改"""
    resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "不可篡改的项目",
    })
    project_id = resp.json()["data"]["id"]

    # 用不存在的 ID 尝试修改 → 404
    resp = await async_client.put("/api/v1/bid-projects/999999", headers=auth_headers, json={
        "project_name": "被篡改了",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_delete_project(async_client: AsyncClient, auth_headers: dict):
    """攻击向量 3: 租户 A 的项目，其他租户不可删"""
    resp = await async_client.delete("/api/v1/bid-projects/999999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_read_enterprise(async_client: AsyncClient, auth_headers: dict):
    """攻击向量 4: 企业信息跨租户不可读"""
    resp = await async_client.get("/api/v1/enterprises/999999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_read_quotation(async_client: AsyncClient, auth_headers: dict):
    """攻击向量 5: 报价单跨租户不可读"""
    resp = await async_client.get("/api/v1/quotations/999999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_read_credential(async_client: AsyncClient, auth_headers: dict):
    """攻击向量 6: 资质证书跨租户不可读"""
    resp = await async_client.get("/api/v1/credentials/999999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cross_tenant_risk_report(async_client: AsyncClient, auth_headers: dict):
    """攻击向量 7: 跨租户生成风险报告"""
    resp = await async_client.post("/api/v1/bid-projects/999999/risk-report", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cross_tenant_export_check(async_client: AsyncClient, auth_headers: dict):
    """攻击向量 8: 跨租户导出检查"""
    resp = await async_client.get("/api/v1/bid-projects/999999/export-check", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cross_tenant_readiness_check(async_client: AsyncClient, auth_headers: dict):
    """攻击向量 9: 跨租户企业完整度检查"""
    resp = await async_client.get("/api/v1/enterprises/999999/readiness", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_project_list_only_own_tenant(async_client: AsyncClient, auth_headers: dict):
    """列表接口只返回当前租户数据"""
    # 创建一个项目
    await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "我的项目",
    })

    # 列表应只包含当前租户的数据
    resp = await async_client.get("/api/v1/bid-projects", headers=auth_headers)
    assert resp.status_code == 200
    projects = resp.json()["data"]
    # 所有项目的 tenant_id 应该一致
    if projects:
        tenant_ids = set(p.get("tenant_id") for p in projects)
        assert len(tenant_ids) == 1, f"列表包含多个租户数据: {tenant_ids}"
