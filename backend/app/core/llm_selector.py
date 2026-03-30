"""
LLM 模型统一选择器 — 从 llm_registry.yaml 读取模型名 + fallback 链

架构红线：
  - 所有 LLM 调用必须通过 LLMSelector.get_model("task_type") 获取模型名
  - 严禁在业务代码中硬编码模型名
  - 首选模型不可用时自动回退到 fallback 链中的下一个模型

使用示例:
    from app.core.llm_selector import LLMSelector

    model = LLMSelector.get_model("bid_section_generate")
    config = LLMSelector.get_config("tender_parse")
"""
import os
from typing import Optional

import yaml

# llm_registry.yaml 文件路径
_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "llm_registry.yaml",
)

# 缓存，避免每次调用都读文件
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

    # 文件未修改，直接返回缓存
    if _registry_cache is not None and current_mtime == _registry_mtime:
        return _registry_cache

    with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    _registry_cache = data
    _registry_mtime = current_mtime
    return data


class LLMSelector:
    """LLM 模型统一选择器

    从 llm_registry.yaml 按 task_type 读取模型配置，
    支持 fallback 链和热更新（文件修改后自动重新加载）。
    """

    @staticmethod
    def get_model(task_type: str) -> str:
        """获取指定任务类型的首选模型名

        Args:
            task_type: 任务类型（如 "bid_section_generate", "tender_parse"）

        Returns:
            模型名字符串（如 "deepseek-chat"）

        Raises:
            KeyError: task_type 不存在于注册表中
            ValueError: task_type 存在但 models 列表为空
        """
        config = LLMSelector.get_config(task_type)
        models = config.get("models", [])
        if not models:
            raise ValueError(f"任务 '{task_type}' 的 models 列表为空")
        return models[0]

    @staticmethod
    def get_all_models(task_type: str) -> list[str]:
        """获取指定任务类型的全部 fallback 模型列表

        Args:
            task_type: 任务类型

        Returns:
            模型名列表（按优先级排序）
        """
        config = LLMSelector.get_config(task_type)
        return config.get("models", [])

    @staticmethod
    def get_config(task_type: str) -> dict:
        """获取指定任务类型的完整配置

        Args:
            task_type: 任务类型

        Returns:
            配置字典，包含 models, temperature, max_tokens 等

        Raises:
            KeyError: task_type 不存在于注册表中
        """
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
        """获取指定任务类型的 temperature 配置"""
        config = LLMSelector.get_config(task_type)
        return float(config.get("temperature", 0.3))

    @staticmethod
    def get_max_tokens(task_type: str) -> int:
        """获取指定任务类型的 max_tokens 配置"""
        config = LLMSelector.get_config(task_type)
        return int(config.get("max_tokens", 2048))

    @staticmethod
    def list_task_types() -> list[str]:
        """列出所有可用的任务类型"""
        registry = _load_registry()
        return list(registry.get("tasks", {}).keys())
