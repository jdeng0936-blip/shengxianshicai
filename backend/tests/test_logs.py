"""
日志基础设施测试 — 确认 Python logging 配置正常
"""
import logging


def test_logger_is_configured():
    """应用 logger 可正常获取且不为 None"""
    logger = logging.getLogger("app")
    assert logger is not None
    assert logger.name == "app"


def test_logger_can_emit():
    """logger 可正常输出日志而不报错"""
    logger = logging.getLogger("app.tests")
    # 不应抛出异常
    logger.info("test log message from pytest")
    logger.warning("test warning from pytest")
