"""
特征开关 — 从 llm_registry.yaml 的 features 段读取功能启用状态

使用方式:
    from app.core.feature_gate import feature_enabled

    if feature_enabled("reactive_compact"):
        result = await reactive_compact(chunks, max_tokens)
    else:
        result = chunks[:max_tokens]  # 降级: 简单截断

设计要点:
  - 与 llm_registry.yaml 共享同一个 YAML 文件，无需额外配置文件
  - 支持热加载（文件修改后自动刷新，无需重启）
  - 未定义的特征默认 False（安全侧倒）
"""
import logging

logger = logging.getLogger("freshbid.feature_gate")


def feature_enabled(name: str, default: bool = False) -> bool:
    """查询特征开关是否启用

    Args:
        name: 特征名称（对应 llm_registry.yaml 中 features 下的 key）
        default: 未定义时的默认值（默认 False，安全侧倒）

    Returns:
        True 表示功能启用，False 表示禁用
    """
    from app.core.llm_selector import _load_registry
    try:
        registry = _load_registry()
        features = registry.get("features", {})
        enabled = features.get(name, default)
        return bool(enabled)
    except Exception:
        logger.warning("特征开关读取失败，降级为默认值: %s=%s", name, default)
        return default


def get_all_features() -> dict[str, bool]:
    """获取所有特征开关状态（供监控接口）"""
    from app.core.llm_selector import _load_registry
    try:
        registry = _load_registry()
        features = registry.get("features", {})
        return {k: bool(v) for k, v in features.items()}
    except Exception:
        return {}
