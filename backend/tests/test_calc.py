"""
计算引擎 API 测试 — 支护/通风/循环 三个计算接口
"""
import pytest


@pytest.mark.asyncio
async def test_calc_support(async_client, auth_headers):
    """支护计算 → 200 + 结果包含安全系数"""
    resp = await async_client.post("/api/v1/calc/support", json={
        "rock_class": "III",
        "section_form": "矩形",
        "section_width": 4.5,
        "section_height": 3.2,
        "bolt_spacing": 1000,
        "cable_count": 3,
    }, headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()["data"]
    # 检查关键计算结果字段
    assert "safety_factor" in result
    assert "bolt_force" in result
    assert result["section_area"] == 14.4


@pytest.mark.asyncio
async def test_calc_ventilation(async_client, auth_headers):
    """通风计算 → 200 + 结果包含需风量和风机推荐"""
    resp = await async_client.post("/api/v1/calc/ventilation", json={
        "gas_emission": 3.0,
        "gas_level": "低瓦斯",
        "section_area": 14.4,
        "excavation_length": 800,
        "max_workers": 25,
    }, headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()["data"]
    # 检查实际返回字段
    assert "q_required" in result
    assert "recommended_fan" in result
    assert result["q_required"] > 0


@pytest.mark.asyncio
async def test_calc_cycle(async_client, auth_headers):
    """循环作业计算 → 200 + 结果包含日进尺和月进尺"""
    resp = await async_client.post("/api/v1/calc/cycle", json={
        "dig_method": "综掘",
        "cut_depth": 0.8,
        "shifts_per_day": 3,
    }, headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()["data"]
    assert "daily_advance" in result
    assert "monthly_advance" in result
    assert result["daily_advance"] > 0
