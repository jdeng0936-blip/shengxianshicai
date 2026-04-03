"""
LLM 熔断器 + 自动容灾测试

严禁调用真实 LLM API，全部使用 mock。
"""
import time
import pytest
import asyncio

from app.core.circuit_breaker import (
    is_available,
    record_success,
    record_failure,
    get_status,
    reset,
    CircuitState,
    FAILURE_THRESHOLD,
    RECOVERY_TIMEOUT,
)
from app.core.llm_selector import LLMSelector


# 每个测试前重置全局状态
@pytest.fixture(autouse=True)
def clean_circuits():
    reset()
    yield
    reset()


# ═══════════════════════════════════════════════════════════
# 熔断器状态机
# ═══════════════════════════════════════════════════════════

class TestCircuitBreaker:

    def test_initial_state_available(self):
        """初始状态可用"""
        assert is_available("openai") is True
        status = get_status("openai")
        assert status["state"] == "closed"

    def test_single_failure_still_available(self):
        """单次失败不触发熔断"""
        record_failure("openai", "timeout")
        assert is_available("openai") is True

    def test_threshold_triggers_open(self):
        """连续 N 次失败触发熔断"""
        for i in range(FAILURE_THRESHOLD):
            record_failure("openai", f"error_{i}")
        assert is_available("openai") is False
        assert get_status("openai")["state"] == "open"

    def test_success_resets_count(self):
        """成功重置失败计数"""
        record_failure("openai", "e1")
        record_failure("openai", "e2")
        record_success("openai")
        record_failure("openai", "e3")
        # 只有 1 次连续失败，不触发
        assert is_available("openai") is True

    def test_success_recovers_from_open(self):
        """成功将 OPEN 恢复为 CLOSED"""
        for i in range(FAILURE_THRESHOLD):
            record_failure("openai", f"e{i}")
        assert is_available("openai") is False
        # 强制恢复
        record_success("openai")
        assert is_available("openai") is True
        assert get_status("openai")["state"] == "closed"

    def test_independent_providers(self):
        """不同 provider 独立熔断"""
        for i in range(FAILURE_THRESHOLD):
            record_failure("openai", f"e{i}")
        assert is_available("openai") is False
        assert is_available("gemini") is True

    def test_reset_clears_state(self):
        """reset 清除所有状态"""
        for i in range(FAILURE_THRESHOLD):
            record_failure("openai", f"e{i}")
        reset()
        assert is_available("openai") is True

    def test_reset_single_provider(self):
        """reset 单个 provider"""
        for i in range(FAILURE_THRESHOLD):
            record_failure("openai", f"e{i}")
            record_failure("gemini", f"e{i}")
        reset("openai")
        assert is_available("openai") is True
        assert is_available("gemini") is False

    def test_stats_tracking(self):
        """统计数据正确"""
        record_success("openai")
        record_failure("openai", "e1")
        record_success("openai")
        status = get_status("openai")
        assert status["total_calls"] == 3
        assert status["total_failures"] == 1


# ═══════════════════════════════════════════════════════════
# LLMSelector 熔断集成
# ═══════════════════════════════════════════════════════════

class TestSelectorWithCircuitBreaker:

    def test_skips_tripped_provider(self):
        """get_client_config 跳过熔断的 provider"""
        # 熔断 openai
        for i in range(FAILURE_THRESHOLD):
            record_failure("openai", f"e{i}")

        cfg = LLMSelector.get_client_config("bid_section_generate")
        # bid_section_generate 的 models: ["openai/gpt-5.4", "gemini/...", "deepseek/..."]
        # openai 熔断后应选 gemini
        assert cfg["provider"] != "openai"

    def test_all_tripped_falls_back_to_first(self):
        """全部熔断时降级到第一个"""
        for provider in ["openai", "claude", "gemini", "deepseek"]:
            for i in range(FAILURE_THRESHOLD):
                record_failure(provider, f"e{i}")

        cfg = LLMSelector.get_client_config("bid_section_generate")
        # 全部熔断 → 降级第一个（bid_section_generate T1 首选 openai）
        assert cfg["provider"] == "openai"

    def test_healthy_provider_selected_first(self):
        """健康的 provider 被优先选择"""
        cfg = LLMSelector.get_client_config("bid_section_generate")
        # 无熔断 → 选第一个
        assert cfg["provider"] == "openai"


# ═══════════════════════════════════════════════════════════
# call_with_fallback
# ═══════════════════════════════════════════════════════════

class TestCallWithFallback:

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """第一个 provider 成功"""
        call_log = []

        async def mock_call(cfg):
            call_log.append(cfg["provider"])
            return "ok"

        result = await LLMSelector.call_with_fallback("bid_section_generate", mock_call)
        assert result == "ok"
        assert len(call_log) == 1

    @pytest.mark.asyncio
    async def test_fallback_on_first_failure(self):
        """第一个失败，自动切到第二个"""
        call_log = []

        async def mock_call(cfg):
            call_log.append(cfg["provider"])
            if cfg["provider"] == "openai":
                raise ConnectionError("API down")
            return "fallback_ok"

        result = await LLMSelector.call_with_fallback("bid_section_generate", mock_call)
        assert result == "fallback_ok"
        assert len(call_log) == 2
        assert call_log[0] == "openai"
        # 第二个是 gemini 或 deepseek

    @pytest.mark.asyncio
    async def test_all_fail_raises(self):
        """全部失败抛 RuntimeError"""
        async def mock_call(cfg):
            raise ConnectionError(f"{cfg['provider']} down")

        with pytest.raises(RuntimeError, match="全部失败"):
            await LLMSelector.call_with_fallback("bid_section_generate", mock_call)

    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self):
        """超时触发 fallback"""
        call_log = []

        async def mock_call(cfg):
            call_log.append(cfg["provider"])
            if cfg["provider"] == "openai":
                await asyncio.sleep(10)  # 会被超时取消
            return "fast_ok"

        result = await LLMSelector.call_with_fallback(
            "bid_section_generate", mock_call, timeout=0.1
        )
        assert result == "fast_ok"
        assert len(call_log) >= 2

    @pytest.mark.asyncio
    async def test_circuit_breaker_updated_after_call(self):
        """调用后熔断器状态正确更新"""
        async def mock_call(cfg):
            if cfg["provider"] == "openai":
                raise ConnectionError("down")
            return "ok"

        await LLMSelector.call_with_fallback("bid_section_generate", mock_call)

        # openai 应记录一次失败
        status = get_status("openai")
        assert status["total_failures"] == 1

    @pytest.mark.asyncio
    async def test_skips_tripped_provider_in_fallback(self):
        """call_with_fallback 跳过已熔断的 provider"""
        # 先熔断 openai
        for i in range(FAILURE_THRESHOLD):
            record_failure("openai", f"e{i}")

        call_log = []

        async def mock_call(cfg):
            call_log.append(cfg["provider"])
            return "ok"

        await LLMSelector.call_with_fallback("bid_section_generate", mock_call)
        # 不应调用 openai
        assert "openai" not in call_log
