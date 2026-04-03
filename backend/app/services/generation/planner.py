"""
Node 1: 大纲规划 — 根据招标要求 + 章节模板输出 JSON 结构化章节计划

输入: 项目 ID、招标要求列表、客户类型
输出: 章节计划列表（编号、标题、关键点、对应评分项）
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from openai import AsyncOpenAI

from app.core.llm_selector import LLMSelector
from app.services.bid_chapter_engine import (
    get_chapter_templates,
    map_requirements_to_chapters,
    build_chapter_outline,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.bid_project import BidProject

logger = logging.getLogger(__name__)


@dataclass
class ChapterPlan:
    """单章节计划结构"""
    chapter_no: str
    title: str
    key_points: list[str] = field(default_factory=list)
    mapped_requirements: list[int] = field(default_factory=list)
    estimated_words: int = 800


# ── LLM prompt ────────────────────────────────────────────
_PLANNER_SYSTEM = (
    "你是一位资深的生鲜食材配送投标文件策划专家。"
    "根据招标要求和章节大纲，为每个章节提炼 3-6 个必须覆盖的关键点。"
    "输出严格的 JSON 数组，每个元素格式: "
    '{"chapter_no": "第X章", "key_points": ["要点1", ...], "estimated_words": 800}'
)


async def _call_llm_for_key_points(outline_text: str) -> list[dict]:
    """调用 LLM 提取各章节关键点（带自动容灾 fallback）"""
    temperature = LLMSelector.get_temperature("bid_section_generate")

    async def _do_call(cfg: dict) -> list[dict]:
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )
        resp = await client.chat.completions.create(
            model=cfg["model"],
            temperature=temperature,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user", "content": outline_text},
            ],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "[]"
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed.get("chapters", [])
        return parsed

    return await LLMSelector.call_with_fallback("bid_section_generate", _do_call)


def _build_plans_from_templates(
    templates: list[dict],
    req_mapping: dict[str, list[dict]],
) -> list[ChapterPlan]:
    """纯模板方式构建章节计划（LLM 不可用时的 fallback）"""
    plans = []
    for tmpl in templates:
        ch_no = tmpl["chapter_no"]
        reqs = req_mapping.get(ch_no, [])
        plans.append(ChapterPlan(
            chapter_no=ch_no,
            title=tmpl["title"],
            key_points=[r.get("content", "")[:80] for r in reqs] or tmpl.get("keywords", []),
            mapped_requirements=[r["id"] for r in reqs if "id" in r],
            estimated_words=1200 if reqs else 600,
        ))
    return plans


async def plan_outline(
    session: AsyncSession,
    project: BidProject,
    customer_type: Optional[str] = None,
) -> list[ChapterPlan]:
    """
    大纲规划节点

    根据招标文件解析出的要求 + 章节模板，生成结构化章节计划。
    调用 LLM 对评分标准做智能映射，确定每章必须覆盖的关键点。

    Args:
        session: 数据库会话
        project: 投标项目（含已解析的 requirements）
        customer_type: 客户类型（学校/医院/政府/企业），影响模板选择

    Returns:
        章节计划列表，按 chapter_no 排序
    """
    ct = customer_type or project.customer_type
    templates = get_chapter_templates(ct)

    # 将 requirements 转为 dict 列表供 bid_chapter_engine 使用
    req_dicts = []
    for req in (project.requirements or []):
        req_dicts.append({
            "id": req.id,
            "content": req.content,
            "category": req.category,
            "max_score": req.max_score,
            "score_weight": req.score_weight,
            "is_mandatory": req.is_mandatory,
        })

    req_mapping = map_requirements_to_chapters(req_dicts, ct)

    # 构建大纲文本供 LLM 分析
    outline_parts = []
    for tmpl in templates:
        ch_no = tmpl["chapter_no"]
        mapped = req_mapping.get(ch_no, [])
        outline_parts.append(build_chapter_outline(ch_no, tmpl["title"], mapped, ct))
    full_outline = "\n\n".join(outline_parts)

    # 调用 LLM 提取关键点，失败时降级到纯模板方案
    try:
        llm_plans = await _call_llm_for_key_points(full_outline)
        llm_map = {p["chapter_no"]: p for p in llm_plans if "chapter_no" in p}
    except Exception as e:
        logger.warning("Node1 LLM 调用失败，降级到模板方案: %s", e)
        return _build_plans_from_templates(templates, req_mapping)

    # 合并 LLM 输出与模板信息
    plans = []
    for tmpl in templates:
        ch_no = tmpl["chapter_no"]
        reqs = req_mapping.get(ch_no, [])
        llm_info = llm_map.get(ch_no, {})

        plans.append(ChapterPlan(
            chapter_no=ch_no,
            title=tmpl["title"],
            key_points=llm_info.get("key_points", tmpl.get("keywords", [])),
            mapped_requirements=[r["id"] for r in reqs if "id" in r],
            estimated_words=llm_info.get("estimated_words", 800),
        ))

    return plans
