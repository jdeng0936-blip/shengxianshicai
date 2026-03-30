"""
投标项目 API 端点测试 — 需要数据库连接 (集成测试)

测试矩阵:
  - BidProject CRUD
  - 章节初始化
  - 导出端点
  - 合规检查端点
  - 报价初始化端点
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_projects(async_client: AsyncClient, auth_headers: dict):
    """GET /bid-projects 返回列表"""
    resp = await async_client.get("/api/v1/bid-projects", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


@pytest.mark.asyncio
async def test_create_project(async_client: AsyncClient, auth_headers: dict):
    """POST /bid-projects 创建投标项目"""
    resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "测试学校食材配送项目",
        "tender_org": "XX市第一中学",
        "customer_type": "school",
        "tender_type": "open",
        "budget_amount": 500000,
    })
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["project_name"] == "测试学校食材配送项目"
    assert data["customer_type"] == "school"
    assert data["status"] == "draft"
    return data["id"]


@pytest.mark.asyncio
async def test_get_project(async_client: AsyncClient, auth_headers: dict):
    """GET /bid-projects/{id} 获取详情"""
    # 先创建
    create_resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "详情测试项目",
    })
    project_id = create_resp.json()["data"]["id"]

    # 再获取
    resp = await async_client.get(f"/api/v1/bid-projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == project_id
    assert "requirements" in data
    assert "chapters" in data


@pytest.mark.asyncio
async def test_update_project(async_client: AsyncClient, auth_headers: dict):
    """PUT /bid-projects/{id} 更新项目"""
    create_resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "更新前",
    })
    project_id = create_resp.json()["data"]["id"]

    resp = await async_client.put(f"/api/v1/bid-projects/{project_id}", headers=auth_headers, json={
        "project_name": "更新后",
        "budget_amount": 1000000,
    })
    assert resp.status_code == 200
    assert resp.json()["data"]["project_name"] == "更新后"


@pytest.mark.asyncio
async def test_delete_project(async_client: AsyncClient, auth_headers: dict):
    """DELETE /bid-projects/{id} 删除项目"""
    create_resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "待删除",
    })
    project_id = create_resp.json()["data"]["id"]

    resp = await async_client.delete(f"/api/v1/bid-projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200

    # 确认已删除
    get_resp = await async_client.get(f"/api/v1/bid-projects/{project_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_init_chapters(async_client: AsyncClient, auth_headers: dict):
    """POST /bid-projects/{id}/init-chapters 初始化 9 章"""
    create_resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "章节初始化测试",
        "customer_type": "school",
    })
    project_id = create_resp.json()["data"]["id"]

    resp = await async_client.post(
        f"/api/v1/bid-projects/{project_id}/init-chapters", headers=auth_headers
    )
    assert resp.status_code == 200
    chapters = resp.json()["data"]
    assert len(chapters) == 9
    assert chapters[0]["chapter_no"] == "第一章"


@pytest.mark.asyncio
async def test_init_chapters_idempotent(async_client: AsyncClient, auth_headers: dict):
    """重复初始化不会创建重复章节"""
    create_resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "幂等性测试",
        "customer_type": "hospital",
    })
    project_id = create_resp.json()["data"]["id"]

    # 两次初始化
    resp1 = await async_client.post(f"/api/v1/bid-projects/{project_id}/init-chapters", headers=auth_headers)
    resp2 = await async_client.post(f"/api/v1/bid-projects/{project_id}/init-chapters", headers=auth_headers)
    assert len(resp1.json()["data"]) == len(resp2.json()["data"])


@pytest.mark.asyncio
async def test_export_without_chapters_fails(async_client: AsyncClient, auth_headers: dict):
    """无章节时导出 → 400"""
    create_resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "空项目导出测试",
    })
    project_id = create_resp.json()["data"]["id"]

    resp = await async_client.post(f"/api/v1/bid-projects/{project_id}/export", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_compliance_check_empty_project(async_client: AsyncClient, auth_headers: dict):
    """空项目合规检查 → 返回空结果"""
    create_resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "合规检查测试",
    })
    project_id = create_resp.json()["data"]["id"]

    resp = await async_client.post(
        f"/api/v1/bid-projects/{project_id}/compliance-check", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["passed"] == 0


@pytest.mark.asyncio
async def test_init_quotation(async_client: AsyncClient, auth_headers: dict):
    """POST /bid-projects/{id}/init-quotation 自动初始化报价单"""
    create_resp = await async_client.post("/api/v1/bid-projects", headers=auth_headers, json={
        "project_name": "报价测试",
        "budget_amount": 300000,
    })
    project_id = create_resp.json()["data"]["id"]

    resp = await async_client.post(
        f"/api/v1/bid-projects/{project_id}/init-quotation?discount_rate=0.1",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    sheet = resp.json()["data"]
    assert sheet["version"] == 1
    assert sheet["discount_rate"] == 0.1
    assert len(sheet["items"]) > 0


@pytest.mark.asyncio
async def test_nonexistent_project_404(async_client: AsyncClient, auth_headers: dict):
    """访问不存在的项目 → 404"""
    resp = await async_client.get("/api/v1/bid-projects/999999", headers=auth_headers)
    assert resp.status_code == 404
