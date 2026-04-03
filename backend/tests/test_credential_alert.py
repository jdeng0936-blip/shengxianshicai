"""
资质到期预警服务测试 — 纯日期计算，使用 mock 数据库
"""
import pytest
from datetime import date
from app.services.credential_alert_service import (
    _parse_date,
    _classify_alert,
    CredentialAlert,
    CredentialAlertReport,
)


# ═══════════════════════════════════════════════════════════
# 日期工具
# ═══════════════════════════════════════════════════════════

class TestParseDate:

    def test_standard_format(self):
        assert _parse_date("2026-04-10") == date(2026, 4, 10)

    def test_slash_format(self):
        assert _parse_date("2026/04/10") == date(2026, 4, 10)

    def test_dot_format(self):
        assert _parse_date("2026.04.10") == date(2026, 4, 10)

    def test_none(self):
        assert _parse_date(None) is None

    def test_empty(self):
        assert _parse_date("") is None

    def test_invalid(self):
        assert _parse_date("无期限") is None

    def test_with_spaces(self):
        assert _parse_date(" 2026-04-10 ") == date(2026, 4, 10)


# ═══════════════════════════════════════════════════════════
# 分级逻辑
# ═══════════════════════════════════════════════════════════

class TestClassifyAlert:

    def test_expired(self):
        level, msg = _classify_alert(-5)
        assert level == "expired"
        assert "过期" in msg

    def test_red_zone(self):
        level, msg = _classify_alert(15)
        assert level == "red"
        assert "紧急" in msg

    def test_orange_zone(self):
        level, msg = _classify_alert(45)
        assert level == "orange"
        assert "尽快" in msg

    def test_yellow_zone(self):
        level, msg = _classify_alert(75)
        assert level == "yellow"
        assert "提前" in msg

    def test_green_zone(self):
        level, msg = _classify_alert(180)
        assert level == "green"
        assert "充足" in msg

    def test_boundary_30(self):
        level, _ = _classify_alert(30)
        assert level == "red"

    def test_boundary_0(self):
        level, _ = _classify_alert(0)
        assert level == "red"

    def test_boundary_negative(self):
        level, _ = _classify_alert(-1)
        assert level == "expired"
