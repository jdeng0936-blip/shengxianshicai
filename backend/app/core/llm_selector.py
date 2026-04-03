"""
LLM 模型统一选择器 — 多 Provider 路由

注册表格式升级:
  models: ["provider/model_name", ...]
  例: "openai/gpt-5.4" → 使用 OPENAI_API_KEY + OPENAI_BASE_URL
  例: "gemini/gemini-3.1" → 使用 GEMINI_API_KEY + GEMINI_BASE_URL

架构红线：
  - 所有 LLM 调用必须通过 LLMSelector 获取模型名和客户端配置
  - 严禁在业务代码中硬编码模型名或 API Key
  - 向后兼容: 不带 provider 前缀的模型名默认走 OPENAI_* 配置

使用示例:
    from app.core.llm_selector import LLMSelector

    # 获取模型名（纯字符串，用于 API 调用的 model 参数）
    model = LLMSelector.get_model("bid_section_generate")  # → "gpt-5.4"

    # 获取完整客户端配置（含 api_key + base_url）
    client_cfg = LLMSelector.get_client_config("bid_section_generate")
    # → {"api_key": "sk-xxx", "base_url": "https://api.openai.com/v1", "model": "gpt-5.4"}
"""
import os
from typing import Optional

import yaml

_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "llm_registry.yaml",
)

_registry_cache: Optional[dict] = None
_registry_mtime: float = 0.0


def _load_registry() -> dict:
    """加载并缓存 llm_registry.yaml（文件变更时自动刷新）"""
    global _registry_cache, _registry_mtime

    try:
        current_mtime = os.path.getmtime(_REGISTRY_PATH)
    except OSError:
        if _registry_cache is not None:
            return _registry_cache
        raise FileNotFoundError(f"LLM 注册表不存在: {_REGISTRY_PATH}")

    if _registry_cache is not None and current_mtime == _registry_mtime:
        return _registry_cache

    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    _registry_cache = data
    _registry_mtime = current_mtime
    return data


def _parse_model_ref(model_ref: str) -> tuple[str, str]:
    """解析 'provider/model_name' 格式

    Returns:
        (provider, model_name)
        无 provider 前缀时默认 provider="openai"
    """
    if "/" in model_ref:
        provider, model_name = model_ref.split("/", 1)
        return provider, model_name
    return "openai", model_ref


def _get_provider_config(provider: str) -> dict:
    """根据 provider 名获取 API Key + Base URL

    从 settings 中读取对应 provider 的配置。
    """
    from app.core.config import settings

    configs = {
        "openai": {
            "api_key": settings.OPENAI_API_KEY,
            "base_url": settings.OPENAI_BASE_URL,
        },
        "claude": {
            "api_key": settings.CLAUDE_API_KEY or settings.OPENAI_API_KEY,
            "base_url": settings.CLAUDE_BASE_URL or settings.OPENAI_BASE_URL,
        },
        "gemini": {
            "api_key": settings.GEMINI_API_KEY or settings.OPENAI_API_KEY,
            "base_url": settings.GEMINI_BASE_URL or settings.OPENAI_BASE_URL,
        },
        "deepseek": {
            "api_key": settings.DEEPSEEK_API_KEY or settings.OPENAI_API_KEY,
            "base_url": settings.DEEPSEEK_BASE_URL or settings.OPENAI_BASE_URL,
        },
        "qwen": {
            "api_key": settings.QWEN_API_KEY or settings.OPENAI_API_KEY,
            "base_url": settings.QWEN_BASE_URL or settings.OPENAI_BASE_URL,
        },
    }
    return configs.get(provider, configs["openai"])


class LLMSelector:
    """LLM 模型统一选择器 — 多 Provider 路由

    从 llm_registry.yaml 按 task_type 读取 "provider/model" 配置，
    返回模型名和对应 provider 的客户端参数。
    """

    @staticmethod
    def get_model(task_type: str) -> str:
        """获取首选模型名（纯模型 ID，不含 provider 前缀）

        Returns:
            "gpt-5.4" / "gemini-3.1" 等
        """
        config = LLMSelector.get_config(task_type)
        models = config.get("models", [])
        if not models:
            raise ValueError(f"任务 '{task_type}' 的 models 列表为空")
        _, model_name = _parse_model_ref(models[0])
        return model_name

    @staticmethod
    def get_provider(task_type: str) -> str:
        """获取首选模型的 provider 名

        Returns:
            "openai" / "gemini" / "deepseek" / "qwen"
        """
        config = LLMSelector.get_config(task_type)
        models = config.get("models", [])
        if not models:
            raise ValueError(f"任务 '{task_type}' 的 models 列表为空")
        provider, _ = _parse_model_ref(models[0])
        return provider

    @staticmethod
    def get_client_config(task_type: str) -> dict:
        """获取完整的客户端配置（api_key + base_url + model）

        自动跳过熔断中的 provider，选择第一个可用的。

        Returns:
            {"api_key": "sk-xxx", "base_url": "https://...", "model": "gpt-5.4", "provider": "openai"}
        """
        from app.core.circuit_breaker import is_available

        config = LLMSelector.get_config(task_type)
        models = config.get("models", [])
        if not models:
            raise ValueError(f"任务 '{task_type}' 的 models 列表为空")

        # 选择第一个可用的 provider
        for model_ref in models:
            provider, model_name = _parse_model_ref(model_ref)
            if is_available(provider):
                provider_cfg = _get_provider_config(provider)
                return {
                    "api_key": provider_cfg["api_key"],
                    "base_url": provider_cfg["base_url"],
                    "model": model_name,
                    "provider": provider,
                }

        # 全部熔断时降级到第一个（强制尝试）
        provider, model_name = _parse_model_ref(models[0])
        provider_cfg = _get_provider_config(provider)
        return {
            "api_key": provider_cfg["api_key"],
            "base_url": provider_cfg["base_url"],
            "model": model_name,
            "provider": provider,
        }

    @staticmethod
    def get_all_models(task_type: str) -> list[dict]:
        """获取 fallback 链中所有模型的配置

        Returns:
            [{"provider": "openai", "model": "gpt-5.4", "api_key": ..., "base_url": ...}, ...]
        """
        config = LLMSelector.get_config(task_type)
        result = []
        for ref in config.get("models", []):
            provider, model_name = _parse_model_ref(ref)
            provider_cfg = _get_provider_config(provider)
            result.append({
                "provider": provider,
                "model": model_name,
                "api_key": provider_cfg["api_key"],
                "base_url": provider_cfg["base_url"],
            })
        return result

    @staticmethod
    def get_config(task_type: str) -> dict:
        """获取指定任务类型的完整配置"""
        registry = _load_registry()
        tasks = registry.get("tasks", {})
        if task_type not in tasks:
            raise KeyError(
                f"任务类型 '{task_type}' 不存在于 llm_registry.yaml 中。"
                f"可用任务: {list(tasks.keys())}"
            )
        return tasks[task_type]

    @staticmethod
    def get_temperature(task_type: str) -> float:
        config = LLMSelector.get_config(task_type)
        return float(config.get("temperature", 0.3))

    @staticmethod
    def get_max_tokens(task_type: str) -> int:
        config = LLMSelector.get_config(task_type)
        return int(config.get("max_tokens", 2048))

    @staticmethod
    async def call_with_fallback(task_type: str, call_fn, timeout: float = 30.0):
        """带自动容灾的 LLM 调用包装器

        遍历 task_type 的 models fallback 链，跳过熔断 provider，
        成功时记录健康状态，失败时记录并尝试下一个。

        Args:
            task_type: 任务类型（对应 llm_registry.yaml 的 key）
            call_fn: 异步调用函数，签名: async (client_config: dict) -> result
                     client_config 含 api_key, base_url, model, provider
            timeout: 单次调用超时秒数

        Returns:
            call_fn 的返回值

        Raises:
            RuntimeError: 所有 provider 均失败
        """
        import asyncio
        from app.core.circuit_breaker import is_available, record_success, record_failure

        all_models = LLMSelector.get_all_models(task_type)
        if not all_models:
            raise ValueError(f"任务 '{task_type}' 无可用模型")

        errors = []
        for cfg in all_models:
            provider = cfg["provider"]
            if not is_available(provider):
                continue

            try:
                result = await asyncio.wait_for(call_fn(cfg), timeout=timeout)
                record_success(provider)
                return result
            except asyncio.TimeoutError:
                msg = f"{provider}/{cfg['model']} 超时 ({timeout}s)"
                record_failure(provider, msg)
                errors.append(msg)
            except Exception as e:
                msg = f"{provider}/{cfg['model']}: {type(e).__name__}: {str(e)[:100]}"
                record_failure(provider, msg)
                errors.append(msg)

        # 全部失败
        raise RuntimeError(
            f"LLM 调用全部失败 (task={task_type}): " + " | ".join(errors)
        )

    @staticmethod
    def list_task_types() -> list[str]:
        registry = _load_registry()
        return list(registry.get("tasks", {}).keys())
