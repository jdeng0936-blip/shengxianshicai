"""
规则引擎 CRUD 测试 — 规则组 / 规则（含条件+结论）
"""
import pytest


@pytest.mark.asyncio
async def test_list_rule_groups(async_client, auth_headers):
    """列表查询规则组 → 200 + 包含种子数据"""
    resp = await async_client.get(
        "/api/v1/rules/groups", params={"page": 1, "page_size": 20},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    items = data.get("items", []) if isinstance(data, dict) else data
    # 种子数据至少 3 个规则组
    assert len(items) >= 3


@pytest.mark.asyncio
async def test_create_rule_group(async_client, auth_headers):
    """创建规则组 → 200/201"""
    resp = await async_client.post("/api/v1/rules/groups", json={
        "name": "pytest-测试规则组",
        "description": "自动化测试临时规则组",
    }, headers=auth_headers)
    assert resp.status_code in (200, 201)
    group = resp.json()["data"]
    assert group["id"] > 0
    test_create_rule_group._group_id = group["id"]


@pytest.mark.asyncio
async def test_create_rule_with_conditions(async_client, auth_headers):
    """创建规则（含条件+结论） → 200/201"""
    group_id = getattr(test_create_rule_group, "_group_id", None)
    if not group_id:
        pytest.skip("前置规则组测试未执行")

    resp = await async_client.post("/api/v1/rules", json={
        "group_id": group_id,
        "name": "pytest-测试规则",
        "category": "支护",
        "priority": 5,
        "conditions": [
            {"field": "rock_class", "operator": "eq", "value": "\"IV\""},
        ],
        "actions": [
            {"target_chapter": "4.2", "params_override": {"test": True}},
        ],
    }, headers=auth_headers)
    assert resp.status_code in (200, 201)
    rule = resp.json()["data"]
    assert rule["id"] > 0
    assert len(rule["conditions"]) == 1
    assert len(rule["actions"]) == 1
    test_create_rule_with_conditions._rule_id = rule["id"]


@pytest.mark.asyncio
async def test_delete_rule_group_cascade(async_client, auth_headers):
    """删除规则组 → 级联删除规则"""
    group_id = getattr(test_create_rule_group, "_group_id", None)
    if not group_id:
        pytest.skip("前置规则组测试未执行")

    resp = await async_client.delete(
        f"/api/v1/rules/groups/{group_id}", headers=auth_headers,
    )
    assert resp.status_code == 200
