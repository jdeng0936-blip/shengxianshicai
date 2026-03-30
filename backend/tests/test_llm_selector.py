"""
LLMSelector 测试 — 注册表读取 / 热更新 / fallback 链
"""
import pytest
from app.core.llm_selector import LLMSelector


class TestLLMSelector:
    """LLM 模型选择器单元测试"""

    def test_get_model_returns_string(self):
        """get_model 返回字符串模型名"""
        model = LLMSelector.get_model("bid_section_generate")
        assert isinstance(model, str)
        assert len(model) > 0

    def test_get_config_returns_dict(self):
        """get_config 返回完整配置字典"""
        config = LLMSelector.get_config("bid_section_generate")
        assert isinstance(config, dict)
        assert "models" in config

    def test_temperature_is_float(self):
        """temperature 返回浮点数"""
        temp = LLMSelector.get_temperature("bid_section_generate")
        assert isinstance(temp, float)
        assert 0.0 <= temp <= 2.0

    def test_max_tokens_is_int(self):
        """max_tokens 返回整数"""
        tokens = LLMSelector.get_max_tokens("bid_section_generate")
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_all_models_returns_list(self):
        """get_all_models 返回 fallback 链列表"""
        models = LLMSelector.get_all_models("tool_calling")
        assert isinstance(models, list)
        assert len(models) >= 1

    def test_nonexistent_task_raises(self):
        """不存在的任务类型 → KeyError"""
        with pytest.raises(KeyError):
            LLMSelector.get_model("nonexistent_task_type_xyz")

    def test_list_task_types(self):
        """列出所有注册的任务类型"""
        task_types = LLMSelector.list_task_types()
        assert isinstance(task_types, list)
        assert "bid_section_generate" in task_types
        assert "tool_calling" in task_types
        assert "compliance_check" in task_types
        assert "embedding" in task_types

    def test_compliance_check_low_temperature(self):
        """合规检查任务应使用低 temperature（安全关键）"""
        temp = LLMSelector.get_temperature("compliance_check")
        assert temp <= 0.3, f"合规检查 temperature={temp} 过高，安全关键任务应 ≤0.3"

    def test_embedding_task_exists(self):
        """embedding 任务已注册"""
        model = LLMSelector.get_model("embedding")
        assert isinstance(model, str)
