"""
LLM 错误分类器 — 按错误类型决定恢复策略

错误分级:
  RATE_LIMIT   → 429 限流，指数退避后重试同一 provider
  OVERLOADED   → 529/503 过载，短暂退避后重试或切换 provider
  CONTEXT_TOO_LONG → prompt 超限，需压缩上下文后重试
  AUTH_ERROR   → 401/403 认证失败，直接切换 provider
  CONTENT_FILTER → 内容安全拦截，切换 provider 或调整 prompt
  TIMEOUT      → 超时，切换 provider
  CONNECTION   → 网络错误，短暂退避后重试同一 provider
  UNKNOWN      → 未知错误，切换 provider

恢复策略:
  retry_same    → 退避后重试同一 provider（不计入熔断失败）
  retry_next    → 立即切换下一个 provider
  compact_retry → 压缩上下文后重试
  fail_fast     → 不重试，直接向上抛出
"""
import asyncio
import logging
import re
from enum import Enum
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("freshbid.llm_errors")


class LLMErrorType(str, Enum):
    """LLM 错误类型"""
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    CONTEXT_TOO_LONG = "context_too_long"
    AUTH_ERROR = "auth_error"
    CONTENT_FILTER = "content_filter"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    UNKNOWN = "unknown"


class RecoveryAction(str, Enum):
    """恢复动作"""
    RETRY_SAME = "retry_same"       # 退避后重试同一 provider
    RETRY_NEXT = "retry_next"       # 切换下一个 provider
    COMPACT_RETRY = "compact_retry" # 压缩上下文后重试
    FAIL_FAST = "fail_fast"         # 不重试


@dataclass
class ClassifiedError:
    """分类后的错误信息"""
    error_type: LLMErrorType
    action: RecoveryAction
    retry_after: float              # 建议等待秒数（0 = 立即）
    should_count_failure: bool      # 是否计入熔断器失败计数
    original_error: Exception
    message: str

    @property
    def is_retryable(self) -> bool:
        return self.action in (RecoveryAction.RETRY_SAME, RecoveryAction.COMPACT_RETRY)


# ── 状态码 / 错误消息 → 错误类型的匹配规则 ──────────────

_STATUS_CODE_PATTERNS = re.compile(
    r"(?:status[_ ]?code|http)[:\s]*(\d{3})",
    re.IGNORECASE,
)

_CONTEXT_LENGTH_PATTERNS = [
    re.compile(r"maximum context length", re.IGNORECASE),
    re.compile(r"token.{0,20}exceed", re.IGNORECASE),
    re.compile(r"prompt.{0,20}too.{0,10}long", re.IGNORECASE),
    re.compile(r"context.{0,20}window", re.IGNORECASE),
    re.compile(r"(\d+)\s*>\s*(\d+)\s*token", re.IGNORECASE),
]

_CONTENT_FILTER_PATTERNS = [
    re.compile(r"content.{0,10}filter", re.IGNORECASE),
    re.compile(r"safety.{0,10}filter", re.IGNORECASE),
    re.compile(r"content.{0,10}policy", re.IGNORECASE),
    re.compile(r"harmful.{0,10}content", re.IGNORECASE),
]

_CONNECTION_ERROR_TYPES = (
    ConnectionError, ConnectionResetError, ConnectionRefusedError,
    ConnectionAbortedError, BrokenPipeError, OSError,
)


def _extract_status_code(error: Exception) -> Optional[int]:
    """从异常中提取 HTTP 状态码"""
    # OpenAI SDK 的 APIStatusError 有 status_code 属性
    if hasattr(error, "status_code"):
        return int(error.status_code)
    # httpx 的 HTTPStatusError
    if hasattr(error, "response") and hasattr(error.response, "status_code"):
        return int(error.response.status_code)
    # 从错误消息中正则提取
    msg = str(error)
    match = _STATUS_CODE_PATTERNS.search(msg)
    if match:
        return int(match.group(1))
    return None


def classify_error(error: Exception) -> ClassifiedError:
    """将原始异常分类为结构化错误信息

    分类优先级: 超时 > 连接 > 状态码 > 消息模式匹配 > 未知
    """
    msg = str(error)

    # ── 超时 ──
    if isinstance(error, asyncio.TimeoutError):
        return ClassifiedError(
            error_type=LLMErrorType.TIMEOUT,
            action=RecoveryAction.RETRY_NEXT,
            retry_after=0,
            should_count_failure=True,
            original_error=error,
            message="请求超时",
        )

    # ── 连接错误 ──
    if isinstance(error, _CONNECTION_ERROR_TYPES):
        return ClassifiedError(
            error_type=LLMErrorType.CONNECTION,
            action=RecoveryAction.RETRY_SAME,
            retry_after=2.0,
            should_count_failure=False,  # 网络抖动不计入熔断
            original_error=error,
            message=f"连接错误: {type(error).__name__}",
        )

    # ── HTTP 状态码 ──
    status = _extract_status_code(error)
    if status:
        if status == 429:
            # 尝试从 header/消息中提取 retry-after
            retry_after = _extract_retry_after(error)
            return ClassifiedError(
                error_type=LLMErrorType.RATE_LIMIT,
                action=RecoveryAction.RETRY_SAME,
                retry_after=retry_after,
                should_count_failure=False,  # 限流不计入熔断
                original_error=error,
                message=f"限流 429，建议 {retry_after:.1f}s 后重试",
            )
        if status in (529, 503):
            return ClassifiedError(
                error_type=LLMErrorType.OVERLOADED,
                action=RecoveryAction.RETRY_NEXT,
                retry_after=5.0,
                should_count_failure=True,
                original_error=error,
                message=f"服务过载 {status}",
            )
        if status in (401, 403):
            return ClassifiedError(
                error_type=LLMErrorType.AUTH_ERROR,
                action=RecoveryAction.RETRY_NEXT,
                retry_after=0,
                should_count_failure=True,
                original_error=error,
                message=f"认证失败 {status}",
            )

    # ── 消息模式匹配: 上下文超限 ──
    for pattern in _CONTEXT_LENGTH_PATTERNS:
        if pattern.search(msg):
            return ClassifiedError(
                error_type=LLMErrorType.CONTEXT_TOO_LONG,
                action=RecoveryAction.COMPACT_RETRY,
                retry_after=0,
                should_count_failure=False,
                original_error=error,
                message="Prompt 超出上下文窗口限制",
            )

    # ── 消息模式匹配: 内容安全 ──
    for pattern in _CONTENT_FILTER_PATTERNS:
        if pattern.search(msg):
            return ClassifiedError(
                error_type=LLMErrorType.CONTENT_FILTER,
                action=RecoveryAction.RETRY_NEXT,
                retry_after=0,
                should_count_failure=False,
                original_error=error,
                message="内容安全过滤拦截",
            )

    # ── 未知错误 ──
    return ClassifiedError(
        error_type=LLMErrorType.UNKNOWN,
        action=RecoveryAction.RETRY_NEXT,
        retry_after=0,
        should_count_failure=True,
        original_error=error,
        message=f"{type(error).__name__}: {msg[:100]}",
    )


def _extract_retry_after(error: Exception) -> float:
    """从 429 响应中提取 retry-after 秒数"""
    # OpenAI SDK 的 response headers
    if hasattr(error, "response") and hasattr(error.response, "headers"):
        ra = error.response.headers.get("retry-after")
        if ra:
            try:
                return float(ra)
            except ValueError:
                pass
    # 从消息中正则提取
    msg = str(error)
    # 模式1: "retry after 30 seconds"
    for pattern in [
        r"retry.{0,20}?(\d+\.?\d*)\s*s",         # retry ... Ns
        r"after\s+(\d+\.?\d*)\s*second",           # after N second(s)
        r"(\d+\.?\d*)\s*seconds?\s*(?:later|wait)", # N seconds later/wait
    ]:
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            return float(match.group(1))
    # 默认退避
    return 5.0


async def exponential_backoff(attempt: int, base: float = 1.0, max_wait: float = 60.0) -> float:
    """指数退避等待

    Args:
        attempt: 第几次重试（从 0 开始）
        base: 基础等待秒数
        max_wait: 最大等待秒数

    Returns:
        实际等待的秒数
    """
    import random
    wait = min(base * (2 ** attempt) + random.uniform(0, 1), max_wait)
    logger.info("指数退避: 等待 %.1f 秒（第 %d 次重试）", wait, attempt + 1)
    await asyncio.sleep(wait)
    return wait
