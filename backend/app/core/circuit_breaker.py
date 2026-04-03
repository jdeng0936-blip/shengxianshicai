"""
LLM Provider 熔断器 — 自动容灾切换

状态机:
  CLOSED  → 正常，允许请求
  OPEN    → 熔断，拒绝请求（直接跳到下一个 provider）
  HALF_OPEN → 试探中，允许少量请求测试恢复

触发规则:
  - 连续 N 次失败 → OPEN（默认 3 次）
  - OPEN 状态持续 T 秒后 → HALF_OPEN（默认 60 秒）
  - HALF_OPEN 请求成功 → CLOSED
  - HALF_OPEN 请求失败 → OPEN（重置冷却期）
"""
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("freshbid")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ProviderCircuit:
    """单个 provider 的熔断状态"""
    provider: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    total_calls: int = 0
    total_failures: int = 0


# 全局配置
FAILURE_THRESHOLD = 3     # 连续失败 N 次触发熔断
RECOVERY_TIMEOUT = 60.0   # 熔断后 N 秒进入半开状态
HALF_OPEN_MAX = 1         # 半开状态允许的最大试探请求数

# 全局状态（进程内存，重启重置）
_circuits: dict[str, ProviderCircuit] = {}


def _get_circuit(provider: str) -> ProviderCircuit:
    if provider not in _circuits:
        _circuits[provider] = ProviderCircuit(provider=provider)
    return _circuits[provider]


def is_available(provider: str) -> bool:
    """检查 provider 是否可用（CLOSED 或 HALF_OPEN）"""
    circuit = _get_circuit(provider)

    if circuit.state == CircuitState.CLOSED:
        return True

    if circuit.state == CircuitState.OPEN:
        # 检查是否到了冷却期
        elapsed = time.time() - circuit.last_failure_time
        if elapsed >= RECOVERY_TIMEOUT:
            circuit.state = CircuitState.HALF_OPEN
            logger.info("熔断器半开: %s（冷却 %.0f 秒后试探）", provider, elapsed)
            return True
        return False

    # HALF_OPEN
    return True


def record_success(provider: str) -> None:
    """记录请求成功"""
    circuit = _get_circuit(provider)
    circuit.total_calls += 1
    circuit.last_success_time = time.time()
    circuit.failure_count = 0

    if circuit.state != CircuitState.CLOSED:
        logger.info("熔断器恢复: %s → CLOSED", provider)
        circuit.state = CircuitState.CLOSED


def record_failure(provider: str, error: Optional[str] = None) -> None:
    """记录请求失败"""
    circuit = _get_circuit(provider)
    circuit.total_calls += 1
    circuit.total_failures += 1
    circuit.failure_count += 1
    circuit.last_failure_time = time.time()

    if circuit.state == CircuitState.HALF_OPEN:
        circuit.state = CircuitState.OPEN
        logger.warning("熔断器重新打开: %s（半开试探失败: %s）", provider, error)
    elif circuit.failure_count >= FAILURE_THRESHOLD:
        circuit.state = CircuitState.OPEN
        logger.warning(
            "熔断器触发: %s → OPEN（连续失败 %d 次: %s）",
            provider, circuit.failure_count, error,
        )


def get_status(provider: str) -> dict:
    """获取 provider 熔断状态（供监控接口）"""
    circuit = _get_circuit(provider)
    return {
        "provider": circuit.provider,
        "state": circuit.state.value,
        "failure_count": circuit.failure_count,
        "total_calls": circuit.total_calls,
        "total_failures": circuit.total_failures,
        "available": is_available(provider),
    }


def get_all_status() -> list[dict]:
    """获取所有 provider 状态"""
    return [get_status(p) for p in _circuits]


def reset(provider: Optional[str] = None) -> None:
    """重置熔断状态（测试/运维用）"""
    if provider:
        _circuits.pop(provider, None)
    else:
        _circuits.clear()
