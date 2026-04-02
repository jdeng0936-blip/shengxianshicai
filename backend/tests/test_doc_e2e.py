"""
DOC-01 端到端集成验证 — 文档生成全链路

NOTE: 原始脚本依赖旧版煤矿系统的 SupportCalcEngine / VentCalcEngine，
      这些模块在生鲜投标转型时已移除。待投标文档生成引擎稳定后重写此测试。
"""
import pytest


@pytest.mark.skip(reason="依赖已移除的煤矿计算引擎(SupportCalcEngine/VentCalcEngine)，待重写")
def test_doc_e2e_generation():
    """全链路文档生成: 参数 → 计算 → 规则 → Word 导出"""
    pass
