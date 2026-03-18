"""
项目管理 CRUD 测试 — 项目创建/列表/更新/删除 + mine_name 验证
"""
import pytest


@pytest.mark.asyncio
async def test_create_project(async_client, auth_headers):
    """创建项目 → 200 + mine_name 正确返回"""
    resp = await async_client.post("/api/v1/projects", json={
        "face_name": "pytest-3301回风巷",
        "mine_id": 1,
        "dig_method": "综掘",
    }, headers=auth_headers)
    assert resp.status_code == 200
    project = resp.json()["data"]
    assert project["id"] > 0
    assert project["face_name"] == "pytest-3301回风巷"
    # P1 修复: mine_name 应正确返回
    assert project.get("mine_name") is not None
    test_create_project._project_id = project["id"]


@pytest.mark.asyncio
async def test_list_projects(async_client, auth_headers):
    """列表查询 → 200 + 包含 mine_name"""
    resp = await async_client.get(
        "/api/v1/projects", params={"page": 1, "page_size": 50},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    items = data if isinstance(data, list) else data.get("items", [])
    assert len(items) >= 1
    # 验证每个项目都有 mine_name
    for p in items:
        assert "mine_name" in p


@pytest.mark.asyncio
async def test_update_project(async_client, auth_headers):
    """更新项目 → 200"""
    project_id = getattr(test_create_project, "_project_id", None)
    if not project_id:
        pytest.skip("前置创建测试未执行")
    resp = await async_client.put(
        f"/api/v1/projects/{project_id}",
        json={"description": "pytest更新备注"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_project(async_client, auth_headers):
    """删除项目 → 200（级联删除 params 和 documents）"""
    project_id = getattr(test_create_project, "_project_id", None)
    if not project_id:
        pytest.skip("前置创建测试未执行")
    resp = await async_client.delete(
        f"/api/v1/projects/{project_id}", headers=auth_headers,
    )
    assert resp.status_code == 200
