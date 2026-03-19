"""
反馈飞轮 API 测试

利用 conftest.py 已有的 async_client + auth_headers fixture。
测试前先创建矿井+项目（满足 feedback_log.project_id 外键约束）。
"""
import pytest
import pytest_asyncio


FEEDBACK_URL = "/api/v1/feedback"

# ---------- 测试数据 ----------
VALID_FEEDBACK = {
    "chapter_no": "5.2",
    "chapter_title": "支护设计参数",
    "original_text": "锚杆间距 800×800mm，锚索排距 1600mm",
    "modified_text": "锚杆间距 700×700mm，锚索排距 1400mm",
    "action": "edit",
    "comment": "根据现场实际围岩条件调整",
}


@pytest_asyncio.fixture
async def test_project_id(async_client, auth_headers) -> int:
    """先创建矿井和项目，返回 project_id（满足外键约束）"""
    # 创建矿井，直接从响应取 mine_id
    mine_resp = await async_client.post("/api/v1/system/mines", json={
        "name": "反馈测试矿井", "design_capacity": 1.0
    }, headers=auth_headers)
    mine_id = mine_resp.json()["data"]["id"]

    resp = await async_client.post("/api/v1/projects", json={
        "face_name": "feedback-test-回风巷",
        "mine_id": mine_id,
        "dig_method": "综掘",
    }, headers=auth_headers)
    assert resp.status_code == 200, f"创建项目失败: {resp.text}"
    return resp.json()["data"]["id"]


@pytest.mark.asyncio
async def test_submit_feedback_success(async_client, auth_headers, test_project_id):
    """正常提交一条编辑反馈"""
    payload = {**VALID_FEEDBACK, "project_id": test_project_id}
    resp = await async_client.post(
        FEEDBACK_URL, json=payload, headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "recorded"
    assert "id" in data


@pytest.mark.asyncio
async def test_submit_feedback_missing_field(async_client, auth_headers):
    """缺少必填字段 → 422"""
    incomplete = {"project_id": 1, "chapter_no": "1.0"}
    resp = await async_client.post(
        FEEDBACK_URL, json=incomplete, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_feedback_invalid_action(async_client, auth_headers):
    """非法 action 值 → 422"""
    bad_action = {**VALID_FEEDBACK, "project_id": 999, "action": "unknown"}
    resp = await async_client.post(
        FEEDBACK_URL, json=bad_action, headers=auth_headers
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_feedback(async_client, auth_headers, test_project_id):
    """提交后查询能看到记录"""
    payload = {**VALID_FEEDBACK, "project_id": test_project_id}
    await async_client.post(FEEDBACK_URL, json=payload, headers=auth_headers)

    resp = await async_client.get(
        f"{FEEDBACK_URL}?project_id={test_project_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    items = resp.json()["data"]
    assert isinstance(items, list)
    assert len(items) >= 1
    assert items[0]["chapter_no"] == "5.2"


@pytest.mark.asyncio
async def test_feedback_stats(async_client, auth_headers, test_project_id):
    """提交多条后统计端点正确返回"""
    accept_data = {**VALID_FEEDBACK, "project_id": test_project_id, "action": "accept"}
    reject_data = {
        **VALID_FEEDBACK,
        "project_id": test_project_id,
        "action": "reject",
        "chapter_no": "7.1",
    }
    await async_client.post(FEEDBACK_URL, json=accept_data, headers=auth_headers)
    await async_client.post(FEEDBACK_URL, json=reject_data, headers=auth_headers)

    resp = await async_client.get(
        f"{FEEDBACK_URL}/stats?project_id={test_project_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    stats = resp.json()["data"]
    assert stats["total"] >= 2
    assert "accept_rate" in stats
    assert "edit_rate" in stats
    assert "reject_rate" in stats
