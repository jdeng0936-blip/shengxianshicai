"""
LLM 错误分类器测试 — 验证各类错误的分类和恢复策略
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.llm_errors import (
    classify_error,
    LLMErrorType,
    RecoveryAction,
    ClassifiedError,
    exponential_backoff,
)


# ═══════════════════════════════════════════════════════════
# 错误分类测试
# ═══════════════════════════════════════════════════════════

class TestClassifyError:

    def test_timeout_error(self):
        """asyncio.TimeoutError → TIMEOUT + RETRY_NEXT"""
        err = asyncio.TimeoutError()
        result = classify_error(err)
        assert result.error_type == LLMErrorType.TIMEOUT
        assert result.action == RecoveryAction.RETRY_NEXT
        assert result.should_count_failure is True

    def test_connection_error(self):
        """ConnectionError → CONNECTION + RETRY_SAME，不计入熔断"""
        err = ConnectionResetError("Connection reset by peer")
        result = classify_error(err)
        assert result.error_type == LLMErrorType.CONNECTION
        assert result.action == RecoveryAction.RETRY_SAME
        assert result.should_count_failure is False
        assert result.retry_after > 0

    def test_broken_pipe(self):
        """BrokenPipeError → CONNECTION"""
        err = BrokenPipeError()
        result = classify_error(err)
        assert result.error_type == LLMErrorType.CONNECTION

    def test_rate_limit_429_from_status_code_attr(self):
        """status_code=429 属性 → RATE_LIMIT + RETRY_SAME，不计入熔断"""
        err = Exception("Too many requests")
        err.status_code = 429
        result = classify_error(err)
        assert result.error_type == LLMErrorType.RATE_LIMIT
        assert result.action == RecoveryAction.RETRY_SAME
        assert result.should_count_failure is False

    def test_rate_limit_429_from_message(self):
        """错误消息含 status_code 429 → RATE_LIMIT"""
        err = Exception("Error: status_code: 429, Too Many Requests")
        result = classify_error(err)
        assert result.error_type == LLMErrorType.RATE_LIMIT

    def test_overloaded_529(self):
        """status_code=529 → OVERLOADED + RETRY_NEXT"""
        err = Exception("Overloaded")
        err.status_code = 529
        result = classify_error(err)
        assert result.error_type == LLMErrorType.OVERLOADED
        assert result.action == RecoveryAction.RETRY_NEXT
        assert result.should_count_failure is True

    def test_overloaded_503(self):
        """status_code=503 → OVERLOADED"""
        err = Exception("Service Unavailable")
        err.status_code = 503
        result = classify_error(err)
        assert result.error_type == LLMErrorType.OVERLOADED

    def test_auth_error_401(self):
        """status_code=401 → AUTH_ERROR + RETRY_NEXT"""
        err = Exception("Unauthorized")
        err.status_code = 401
        result = classify_error(err)
        assert result.error_type == LLMErrorType.AUTH_ERROR
        assert result.action == RecoveryAction.RETRY_NEXT

    def test_auth_error_403(self):
        """status_code=403 → AUTH_ERROR"""
        err = Exception("Forbidden")
        err.status_code = 403
        result = classify_error(err)
        assert result.error_type == LLMErrorType.AUTH_ERROR

    def test_context_too_long_pattern(self):
        """消息含 'maximum context length' → CONTEXT_TOO_LONG + COMPACT_RETRY"""
        err = Exception("This model's maximum context length is 128000 tokens")
        result = classify_error(err)
        assert result.error_type == LLMErrorType.CONTEXT_TOO_LONG
        assert result.action == RecoveryAction.COMPACT_RETRY
        assert result.should_count_failure is False

    def test_token_exceed_pattern(self):
        """消息含 'token exceeded' → CONTEXT_TOO_LONG"""
        err = Exception("Request token count exceeded the limit")
        result = classify_error(err)
        assert result.error_type == LLMErrorType.CONTEXT_TOO_LONG

    def test_prompt_too_long_pattern(self):
        """消息含 'prompt too long' → CONTEXT_TOO_LONG"""
        err = Exception("prompt is too long: 137500 > 135000")
        result = classify_error(err)
        assert result.error_type == LLMErrorType.CONTEXT_TOO_LONG

    def test_content_filter_pattern(self):
        """消息含 'content filter' → CONTENT_FILTER"""
        err = Exception("The response was filtered due to content filter")
        result = classify_error(err)
        assert result.error_type == LLMErrorType.CONTENT_FILTER
        assert result.action == RecoveryAction.RETRY_NEXT
        assert result.should_count_failure is False

    def test_safety_filter_pattern(self):
        """消息含 'safety filter' → CONTENT_FILTER"""
        err = Exception("Output blocked by safety filter")
        result = classify_error(err)
        assert result.error_type == LLMErrorType.CONTENT_FILTER

    def test_unknown_error(self):
        """未匹配任何模式 → UNKNOWN + RETRY_NEXT"""
        err = ValueError("Something unexpected happened")
        result = classify_error(err)
        assert result.error_type == LLMErrorType.UNKNOWN
        assert result.action == RecoveryAction.RETRY_NEXT
        assert result.should_count_failure is True

    def test_is_retryable_property(self):
        """is_retryable 属性检查"""
        err_429 = Exception("rate limit")
        err_429.status_code = 429
        result = classify_error(err_429)
        assert result.is_retryable is True

        err_401 = Exception("auth")
        err_401.status_code = 401
        result = classify_error(err_401)
        assert result.is_retryable is False


# ═══════════════════════════════════════════════════════════
# retry-after 提取测试
# ═══════════════════════════════════════════════════════════

class TestRetryAfter:

    def test_retry_after_from_header(self):
        """从 response header 提取 retry-after"""
        err = Exception("rate limit")
        err.status_code = 429
        err.response = MagicMock()
        err.response.headers = {"retry-after": "10"}
        result = classify_error(err)
        assert result.retry_after == 10.0

    def test_retry_after_from_message(self):
        """从错误消息提取 retry after N seconds"""
        err = Exception("Rate limited, retry after 30 seconds please")
        err.status_code = 429
        result = classify_error(err)
        assert result.retry_after == 30.0

    def test_retry_after_default(self):
        """无 retry-after 信息时使用默认值"""
        err = Exception("429")
        err.status_code = 429
        result = classify_error(err)
        assert result.retry_after == 5.0


# ═══════════════════════════════════════════════════════════
# 指数退避测试
# ═══════════════════════════════════════════════════════════

class TestExponentialBackoff:

    @pytest.mark.asyncio
    async def test_first_attempt_short(self):
        """第一次退避应较短"""
        import random
        random.seed(42)
        wait = await exponential_backoff(0, base=0.01, max_wait=1.0)
        assert wait < 1.5  # base * 2^0 + jitter，锁定种子后应稳定在 ~1.0 以内

    @pytest.mark.asyncio
    async def test_increases_with_attempts(self):
        """退避时间随重试次数增长（base 足够大以抵消 jitter）"""
        import random
        random.seed(42)
        wait_0 = await exponential_backoff(0, base=1.0, max_wait=100.0)
        random.seed(42)
        wait_3 = await exponential_backoff(3, base=1.0, max_wait=100.0)
        # base=1.0: attempt 0 → ~1s, attempt 3 → ~8s，差距远大于 jitter
        assert wait_3 > wait_0

    @pytest.mark.asyncio
    async def test_max_wait_cap(self):
        """不超过 max_wait"""
        wait = await exponential_backoff(10, base=1.0, max_wait=5.0)
        assert wait <= 6.0  # max_wait + jitter


# ═══════════════════════════════════════════════════════════
# 集成: call_with_fallback + 错误分类
# ═══════════════════════════════════════════════════════════

class TestCallWithFallbackErrorClassification:

    @pytest.mark.asyncio
    async def test_rate_limit_retries_same_provider(self):
        """429 限流应在同一 provider 重试后再切换"""
        from app.core.llm_selector import LLMSelector
        from app.core import circuit_breaker
        circuit_breaker.reset()

        call_count = {"openai": 0, "gemini": 0}
        rate_limit_err = Exception("Too many requests")
        rate_limit_err.status_code = 429
        rate_limit_err.response = MagicMock()
        rate_limit_err.response.headers = {"retry-after": "0.01"}

        async def mock_call(cfg):
            provider = cfg["provider"]
            call_count[provider] = call_count.get(provider, 0) + 1
            if provider == "openai":
                raise rate_limit_err
            return "gemini_success"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                LLMSelector, "get_all_models",
                staticmethod(lambda t: [
                    {"provider": "openai", "model": "gpt-5.4", "api_key": "k", "base_url": "u"},
                    {"provider": "gemini", "model": "gemini-3.1", "api_key": "k", "base_url": "u"},
                ]),
            )
            result = await LLMSelector.call_with_fallback(
                "test_task", mock_call, timeout=5.0, max_retries_per_provider=2,
            )

        assert result == "gemini_success"
        # openai 应该重试了 3 次（初始 + 2 次重试）再切到 gemini
        assert call_count["openai"] == 3
        assert call_count["gemini"] == 1

    @pytest.mark.asyncio
    async def test_auth_error_skips_immediately(self):
        """401 认证错误应立即切换 provider，不重试"""
        from app.core.llm_selector import LLMSelector
        from app.core import circuit_breaker
        circuit_breaker.reset()

        call_count = {"openai": 0, "gemini": 0}
        auth_err = Exception("Unauthorized")
        auth_err.status_code = 401

        async def mock_call(cfg):
            provider = cfg["provider"]
            call_count[provider] = call_count.get(provider, 0) + 1
            if provider == "openai":
                raise auth_err
            return "gemini_success"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                LLMSelector, "get_all_models",
                staticmethod(lambda t: [
                    {"provider": "openai", "model": "gpt-5.4", "api_key": "k", "base_url": "u"},
                    {"provider": "gemini", "model": "gemini-3.1", "api_key": "k", "base_url": "u"},
                ]),
            )
            result = await LLMSelector.call_with_fallback(
                "test_task", mock_call, timeout=5.0,
            )

        assert result == "gemini_success"
        assert call_count["openai"] == 1  # 不重试，直接切换
        assert call_count["gemini"] == 1
