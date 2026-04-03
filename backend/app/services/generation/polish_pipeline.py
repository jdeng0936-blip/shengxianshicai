"""
Node 5: 多轮润色 — 术语统一 / 文风适配 / 逻辑连贯性优化

Round 1 — 规则型术语标准化（毫秒级，无 LLM）
Round 2 — LLM 驱动文风适配 + 逻辑连贯性（可选，按配置触发）

如果 Round 1 无实质修改且未配置 Round 2，提前终止。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import AsyncOpenAI

from app.core.llm_selector import LLMSelector
from app.services.generation.writer import DraftChapter

logger = logging.getLogger(__name__)


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class PolishConfig:
    """润色配置"""
    max_rounds: int = 2
    focus_dimensions: list[str] = field(default_factory=lambda: ["terminology", "style"])
    customer_type: Optional[str] = None


@dataclass
class PolishResult:
    """润色结果"""
    chapter_no: str
    title: str
    content: str
    changes_summary: str
    rounds_applied: int


# ── Round 1: 规则型术语标准化 ─────────────────────────────

# 非标写法 → 标准写法 映射表
_TERMINOLOGY_MAP = {
    "食安法": "《中华人民共和国食品安全法》",
    "食品安全法": "《中华人民共和国食品安全法》",
    "产品质量法": "《中华人民共和国产品质量法》",
    "iso22000": "ISO 22000",
    "ISO22000": "ISO 22000",
    "haccp": "HACCP",
    "Haccp": "HACCP",
    "gb/t 22918": "GB/T 22918",
    "GB/T22918": "GB/T 22918",
    "gb 31621": "GB 31621",
    "GB31621": "GB 31621",
    "SC认证": "SC 生产许可认证",
    "sc认证": "SC 生产许可认证",
    "0~4度": "0~4\u2103",
    "0-4度": "0~4\u2103",
    "-18度": "-18\u2103",
    "零下18度": "-18\u2103",
}

# 口语化 → 正式化 替换
_INFORMAL_MAP = {
    "搞好": "做好",
    "弄好": "完善",
    "没问题": "符合要求",
    "差不多": "基本达到",
    "挺好的": "表现良好",
    "大概": "约",
    "大约": "约",
}


def _apply_terminology_rules(content: str) -> tuple[str, list[str]]:
    """应用术语标准化规则，返回 (修改后内容, 修改记录列表)"""
    changes = []
    result = content

    for old, new in _TERMINOLOGY_MAP.items():
        if old in result and old != new:
            count = result.count(old)
            result = result.replace(old, new)
            changes.append(f"术语标准化: '{old}' → '{new}' ({count}处)")

    for old, new in _INFORMAL_MAP.items():
        if old in result:
            count = result.count(old)
            result = result.replace(old, new)
            changes.append(f"正式化: '{old}' → '{new}' ({count}处)")

    return result, changes


# ── Round 2: LLM 文风适配 ────────────────────────────────

_STYLE_PROMPTS = {
    "school": "面向学校食堂采购方，语气庄重亲切，突出食品安全和营养健康关怀。",
    "hospital": "面向医院采购方，语气严谨专业，突出膳食管理和卫生安全。",
    "government": "面向政府机关采购方，语气正式规范，突出合规性和透明度。",
    "enterprise": "面向企业采购方，语气专业高效，突出服务品质和灵活定制。",
    "canteen": "面向团餐/食堂采购方，语气务实专业，突出规模化供应和成本优势。",
}

_POLISH_SYSTEM = (
    "你是一位投标文件文风润色专家。"
    "请对以下投标文件章节进行文风优化和逻辑连贯性改善。"
    "保留全部技术细节和数值，不增删核心内容，仅优化表达。"
    "直接输出润色后的正文，不加任何解释。"
)


async def _call_llm_polish(content: str, style_hint: str) -> str:
    """调用 LLM 进行文风润色（带自动容灾 fallback）"""
    max_tokens = LLMSelector.get_max_tokens("bid_section_generate")
    user_prompt = f"{style_hint}\n\n== 待润色正文 ==\n{content}"

    async def _do_call(cfg: dict) -> str:
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )
        resp = await client.chat.completions.create(
            model=cfg["model"],
            temperature=0.2,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": _POLISH_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or content

    return await LLMSelector.call_with_fallback("bid_section_generate", _do_call)


# ── 主入口 ────────────────────────────────────────────────

async def polish_draft(
    drafts: list[DraftChapter],
    config: Optional[PolishConfig] = None,
) -> list[PolishResult]:
    """
    多轮润色节点

    Round 1 — 规则型术语标准化（确定性，毫秒级）
    Round 2 — LLM 文风适配 + 逻辑连贯性（按配置启用）

    如果 Round 1 无实质修改且 max_rounds=1，提前终止。

    Args:
        drafts: Node 4 通过合规门禁的草稿章节
        config: 润色配置（轮次、维度、客户类型）

    Returns:
        润色后的章节列表
    """
    cfg = config or PolishConfig()
    results: list[PolishResult] = []

    style_hint = _STYLE_PROMPTS.get(cfg.customer_type or "", "")

    for draft in drafts:
        content = draft.content or ""
        all_changes: list[str] = []
        rounds_done = 0

        # 跳过空内容或占位符章节
        if not content or content.startswith("（"):
            results.append(PolishResult(
                chapter_no=draft.chapter_no,
                title=draft.title,
                content=content,
                changes_summary="跳过: 空内容或占位符",
                rounds_applied=0,
            ))
            continue

        # Round 1: 术语标准化
        if cfg.max_rounds >= 1 and "terminology" in cfg.focus_dimensions:
            content, changes = _apply_terminology_rules(content)
            all_changes.extend(changes)
            rounds_done = 1

        # Round 2: LLM 文风适配
        if cfg.max_rounds >= 2 and "style" in cfg.focus_dimensions:
            try:
                polished = await _call_llm_polish(content, style_hint)
                if polished and polished != content:
                    content = polished
                    all_changes.append("LLM 文风适配与逻辑连贯性优化")
                rounds_done = 2
            except Exception as e:
                logger.warning("章节 %s LLM 润色失败，保留 Round 1 结果: %s",
                               draft.chapter_no, e)
                all_changes.append(f"LLM 润色跳过: {e}")

        summary = "; ".join(all_changes) if all_changes else "无修改"

        results.append(PolishResult(
            chapter_no=draft.chapter_no,
            title=draft.title,
            content=content,
            changes_summary=summary,
            rounds_applied=rounds_done,
        ))

    return results
