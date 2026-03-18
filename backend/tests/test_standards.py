"""
标准库 CRUD 测试 — 文档创建/列表/更新/删除
"""
import pytest


@pytest.mark.asyncio
async def test_list_standards(async_client, auth_headers):
    """列表查询 → 200 + 包含种子数据"""
    resp = await async_client.get(
        "/api/v1/standards", params={"page": 1, "page_size": 20},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    items = data.get("items", []) if isinstance(data, dict) else data
    # 种子数据至少有 8 份文档
    assert len(items) >= 8


@pytest.mark.asyncio
async def test_create_standard(async_client, auth_headers):
    """创建文档 → 200/201 + 返回 id"""
    resp = await async_client.post("/api/v1/standards", json={
        "title": "pytest-测试规范文档",
        "doc_type": "技术规范",
        "version": "test-v1",
    }, headers=auth_headers)
    assert resp.status_code in (200, 201)
    doc = resp.json()["data"]
    assert doc["id"] > 0
    assert doc["title"] == "pytest-测试规范文档"
    # 保存 id 供后续测试使用
    test_create_standard._doc_id = doc["id"]


@pytest.mark.asyncio
async def test_update_standard(async_client, auth_headers):
    """更新文档 → 200"""
    doc_id = getattr(test_create_standard, "_doc_id", None)
    if not doc_id:
        pytest.skip("前置创建测试未执行")
    resp = await async_client.put(
        f"/api/v1/standards/{doc_id}",
        json={"title": "pytest-更新后标题"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["title"] == "pytest-更新后标题"


@pytest.mark.asyncio
async def test_delete_standard(async_client, auth_headers):
    """删除文档 → 200"""
    doc_id = getattr(test_create_standard, "_doc_id", None)
    if not doc_id:
        pytest.skip("前置创建测试未执行")
    resp = await async_client.delete(
        f"/api/v1/standards/{doc_id}", headers=auth_headers,
    )
    assert resp.status_code == 200
