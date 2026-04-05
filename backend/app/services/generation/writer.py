"""
Node 3: 草稿生成 — 结合企业画像 + RAG 结果调用 LLM 生成章节初稿

架构红线: 报价数值禁止用 LLM 输出，必须从 QuotationSheet 计算引擎注入。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from openai import AsyncOpenAI

from app.core.llm_selector import LLMSelector
from app.services.generation.planner import ChapterPlan
from app.services.generation.retriever import RetrievalResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.bid_project import BidProject

logger = logging.getLogger(__name__)

# 报价章节编号 — 此章节不由 LLM 生成正文，仅输出占位提示
_QUOTATION_CHAPTER = "第八章"


@dataclass
class DraftChapter:
    """单章节草稿"""
    chapter_no: str
    title: str
    content: str = ""
    sources_cited: list[str] = field(default_factory=list)
    word_count: int = 0


# ── Prompt 构建 ───────────────────────────────────────────

def _build_rag_block(retrieval: RetrievalResult, max_chars: int = 0) -> str:
    """将 RetrievalResult 格式化为 LLM prompt 中的参考文本块

    当 reactive_compact 特征开关启用且 max_chars > 0 时，
    按优先级（法规 > 模板 > 案例）动态裁剪，确保总长不超限。
    低优先级内容被截断时保留摘要首行，不丢弃。

    Args:
        retrieval: RAG 检索结果
        max_chars: 最大字符数（0 = 不限制，使用固定截断）
    """
    from app.core.feature_gate import feature_enabled

    use_compact = feature_enabled("reactive_compact") and max_chars > 0

    # 三类素材，按优先级排列（法规最高，案例最低）
    sections = []

    if retrieval.std_clauses:
        items = []
        for clause in retrieval.std_clauses[:5]:
            title = clause.get("doc_title", "")
            clause_no = clause.get("clause_no", "")
            text = clause.get("text", "")
            prefix = f"【{title}】" if title else ""
            if clause_no:
                prefix += f"{clause_no} "
            items.append({"prefix": prefix, "text": text, "priority": 3})
        sections.append(("== 法规标准参考 ==", items))

    if retrieval.template_snippets:
        items = []
        for snip in retrieval.template_snippets[:3]:
            name = snip.get("chapter_name", "")
            text = snip.get("text", "")
            items.append({"prefix": f"【{name}】", "text": text, "priority": 2})
        sections.append(("== 知识库模板片段 ==", items))

    if retrieval.bid_cases:
        items = []
        for case in retrieval.bid_cases[:3]:
            name = case.get("chapter_name", "")
            text = case.get("content", "")
            items.append({"prefix": f"【{name}】", "text": text, "priority": 1})
        sections.append(("== 历史中标案例参考 ==", items))

    if not sections:
        return "暂无相关参考资料"

    if not use_compact:
        # 原始行为: 固定截断
        return _format_rag_fixed(sections)

    # 响应式压缩: 按优先级动态分配字符预算
    return _format_rag_compact(sections, max_chars)


def _format_rag_fixed(sections: list) -> str:
    """固定截断模式（原始行为）"""
    # 各优先级的固定截断长度
    _LIMITS = {3: 600, 2: 400, 1: 400}
    parts = []
    for header, items in sections:
        parts.append(header)
        for item in items:
            limit = _LIMITS.get(item["priority"], 400)
            text = item["text"][:limit]
            parts.append(f"{item['prefix']}{text}")
    return "\n".join(parts)


def _format_rag_compact(sections: list, max_chars: int) -> str:
    """响应式压缩模式 — 按优先级动态分配字符预算

    策略:
      1. 高优先级素材（法规）分配 50% 预算
      2. 中优先级（模板）分配 30%
      3. 低优先级（案例）分配 20%
      4. 单条素材超出分配额度时截断，保留首行摘要
    """
    # 按优先级分配预算比例
    _BUDGET_RATIOS = {3: 0.50, 2: 0.30, 1: 0.20}
    parts = []
    used = 0

    for header, items in sections:
        if used >= max_chars:
            break
        parts.append(header)
        used += len(header) + 1

        # 本类别的总预算
        priority = items[0]["priority"] if items else 2
        section_budget = int(max_chars * _BUDGET_RATIOS.get(priority, 0.2))
        section_used = 0

        for item in items:
            if section_used >= section_budget:
                break
            remaining = section_budget - section_used
            text = item["text"]
            if len(text) > remaining:
                # 截断: 保留前 remaining 字符，末尾标记
                text = text[:remaining - 6] + "……(截断)"
            line = f"{item['prefix']}{text}"
            parts.append(line)
            section_used += len(line) + 1
            used += len(line) + 1

    return "\n".join(parts)


def _extract_sources(retrieval: RetrievalResult) -> list[str]:
    """从检索结果中提取引用来源列表"""
    sources = []
    for clause in retrieval.std_clauses[:5]:
        title = clause.get("doc_title", "")
        clause_no = clause.get("clause_no", "")
        if title:
            sources.append(f"{title} {clause_no}".strip())
    for case in retrieval.bid_cases[:3]:
        name = case.get("chapter_name", "")
        if name:
            sources.append(name)
    return sources


def _build_key_points_text(plan: ChapterPlan) -> str:
    """将关键点列表格式化为编号文本"""
    if not plan.key_points:
        return "无特定关键点要求"
    return "\n".join(f"  {i}. {kp}" for i, kp in enumerate(plan.key_points, 1))


def _build_project_info(project: BidProject) -> str:
    """从 BidProject 构建项目信息文本"""
    return (
        f"采购方：{project.tender_org or '未知'}"
        f"（{project.customer_type or '未知'}）\n"
        f"项目名称：{project.project_name}\n"
        f"预算金额：{project.budget_amount or '未知'}元\n"
        f"配送范围：{project.delivery_scope or '未填写'}\n"
        f"配送周期：{project.delivery_period or '未填写'}"
    )


_WRITER_SYSTEM = (
    "你是一位资深的生鲜食材配送投标文件撰写专家。"
    "根据提供的章节大纲、关键点、法规参考和企业信息，撰写专业的投标文件章节正文。"
    "要求：语言专业正式，符合政府采购投标文件规范；"
    "每项技术指标必须有具体数值，禁止写'按规定''视情况'；"
    "引用法规时标注来源。直接输出正文，不输出标题和致谢。"
)


def _build_user_prompt(
    plan: ChapterPlan,
    retrieval: RetrievalResult,
    project_info: str,
    enterprise_info: str,
    rag_max_chars: int = 0,
) -> str:
    """组装完整的 user prompt

    Args:
        rag_max_chars: RAG 参考文本最大字符数（0 = 不限制）
    """
    return (
        f"请编写投标文件【{plan.chapter_no} {plan.title}】章节正文。\n\n"
        f"== 招标项目信息 ==\n{project_info}\n\n"
        f"== 投标企业信息 ==\n{enterprise_info}\n\n"
        f"== 本章必须覆盖的关键点 ==\n{_build_key_points_text(plan)}\n\n"
        f"== 建议篇幅 ==\n约 {plan.estimated_words} 字\n\n"
        f"{_build_rag_block(retrieval, max_chars=rag_max_chars)}"
    )


# ── LLM 调用 ─────────────────────────────────────────────

async def _call_llm(prompt: str) -> str:
    """调用 LLM 生成章节内容（带自动容灾 fallback）"""
    temperature = LLMSelector.get_temperature("bid_section_generate")
    max_tokens = LLMSelector.get_max_tokens("bid_section_generate")

    async def _do_call(cfg: dict) -> str:
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )
        resp = await client.chat.completions.create(
            model=cfg["model"],
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": _WRITER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""

    return await LLMSelector.call_with_fallback("bid_section_generate", _do_call)


# ── 主入口 ────────────────────────────────────────────────

async def generate_draft(
    session: AsyncSession,
    project: BidProject,
    chapter_plans: list[ChapterPlan],
    retrieval_results: list[RetrievalResult],
    enterprise_info: Optional[str] = None,
) -> list[DraftChapter]:
    """
    草稿生成节点

    逐章调用 LLM，将章节计划 + RAG 检索结果 + 企业画像融合为投标文档初稿。
    报价相关章节从 QuotationSheet 注入精确数值，不依赖 LLM 生成。

    Args:
        session: 数据库会话
        project: 投标项目
        chapter_plans: Node 1 输出的章节计划
        retrieval_results: Node 2 输出的检索结果
        enterprise_info: 预构建的企业信息文本块（含资质编号）

    Returns:
        各章节草稿列表
    """
    project_info = _build_project_info(project)
    ent_info = enterprise_info or "企业信息未填写"

    # 按 chapter_no 索引检索结果
    retrieval_map: dict[str, RetrievalResult] = {
        r.chapter_no: r for r in retrieval_results
    }

    drafts: list[DraftChapter] = []

    for plan in chapter_plans:
        # 报价章节跳过 LLM 生成
        if plan.chapter_no == _QUOTATION_CHAPTER:
            drafts.append(DraftChapter(
                chapter_no=plan.chapter_no,
                title=plan.title,
                content="（报价数据由报价引擎自动生成，不使用 AI 撰写）",
                sources_cited=[],
                word_count=0,
            ))
            continue

        retrieval = retrieval_map.get(
            plan.chapter_no, RetrievalResult(chapter_no=plan.chapter_no)
        )

        # 首次尝试: 不限制 RAG 长度
        # 上下文超限时: 压缩 RAG 后重试（响应式压缩）
        content = ""
        rag_max_chars = 0  # 0 = 不限制
        for attempt in range(3):
            prompt = _build_user_prompt(
                plan, retrieval, project_info, ent_info,
                rag_max_chars=rag_max_chars,
            )
            try:
                content = await _call_llm(prompt)
                break
            except Exception as e:
                from app.core.llm_errors import classify_error, LLMErrorType
                classified = classify_error(e)
                if classified.error_type == LLMErrorType.CONTEXT_TOO_LONG and attempt < 2:
                    # 逐步压缩: 3000 → 1500 → 800
                    rag_max_chars = [3000, 1500, 800][attempt]
                    logger.warning(
                        "章节 %s 上下文超限，压缩 RAG 至 %d 字符重试（第 %d 次）",
                        plan.chapter_no, rag_max_chars, attempt + 1,
                    )
                    continue
                logger.error("章节 %s LLM 生成失败: %s", plan.chapter_no, e)
                content = f"（章节生成失败: {e}）"
                break

        sources = _extract_sources(retrieval)

        drafts.append(DraftChapter(
            chapter_no=plan.chapter_no,
            title=plan.title,
            content=content,
            sources_cited=sources,
            word_count=len(content),
        ))

    return drafts
