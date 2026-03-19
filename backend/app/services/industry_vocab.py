"""
行业词库服务 — 懒加载 + 类级缓存

架构铁律：
  - 词库以 JSON 配置文件维护，运维可热更新无需改代码
  - 服务层采用懒加载 + 类级缓存策略
  - RAG 检索时注入评审关注点和常见扣分项
"""
import json
import os
from typing import Optional


class IndustryVocabService:
    """行业词库服务（单例缓存）"""

    # 类级缓存 — 首次加载后内存复用
    _cache: Optional[dict] = None
    _config_path: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "config", "industry_keywords.json"
    )

    @classmethod
    def _load(cls) -> dict:
        """懒加载：首次调用时读取配置文件"""
        if cls._cache is not None:
            return cls._cache
        try:
            with open(cls._config_path, "r", encoding="utf-8") as f:
                cls._cache = json.load(f)
        except FileNotFoundError:
            cls._cache = {}
        return cls._cache

    @classmethod
    def reload(cls) -> None:
        """强制重新加载（运维热更新后调用）"""
        cls._cache = None
        cls._load()

    @classmethod
    def get_industry(cls, industry_type: str) -> Optional[dict]:
        """获取指定行业的词库数据"""
        data = cls._load()
        return data.get(industry_type)

    @classmethod
    def list_industries(cls) -> list[dict]:
        """列出所有可用行业"""
        data = cls._load()
        return [
            {"key": k, "label": v.get("label", k)}
            for k, v in data.items()
        ]

    @classmethod
    def build_prompt_injection(cls, industry_type: str) -> str:
        """构建 System Prompt 注入片段

        返回格式化的行业上下文文本，可直接拼接到 System Prompt 末尾。
        如果行业类型不存在，返回空字符串。
        """
        industry = cls.get_industry(industry_type)
        if not industry:
            return ""

        parts = []

        # 行业标识
        parts.append(f"\n## 当前行业：{industry.get('label', industry_type)}")

        # 核心术语
        keywords = industry.get("core_keywords", [])
        if keywords:
            parts.append(f"\n## 行业术语（生成内容时必须使用专业术语）")
            parts.append("、".join(keywords[:15]))

        # 适用规范
        standards = industry.get("standards", [])
        if standards:
            parts.append(f"\n## 适用规范（引用时必须标注编号和名称）")
            for s in standards:
                parts.append(f"- {s}")

        # 评审关注点
        scoring = industry.get("scoring_focus", [])
        if scoring:
            parts.append(f"\n## 评审关注点（生成内容必须覆盖以下要点）")
            for i, s in enumerate(scoring, 1):
                parts.append(f"{i}. {s}")

        # 常见扣分项
        deductions = industry.get("common_deductions", [])
        if deductions:
            parts.append(f"\n## 常见扣分陷阱（必须主动规避）")
            for i, d in enumerate(deductions, 1):
                parts.append(f"{i}. ⚠️ {d}")

        return "\n".join(parts)

    @classmethod
    def build_rag_context(cls, industry_type: str) -> str:
        """构建 RAG 检索增强上下文

        提取评审关注点和常见扣分项，注入到 RAG 检索 prompt 中，
        提升检索结果与行业评审标准的相关度。
        """
        industry = cls.get_industry(industry_type)
        if not industry:
            return ""

        parts = []
        scoring = industry.get("scoring_focus", [])
        deductions = industry.get("common_deductions", [])

        if scoring:
            parts.append("评审关注点：" + "；".join(scoring))
        if deductions:
            parts.append("常见扣分项：" + "；".join(deductions))

        return "\n".join(parts)
