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

def _build_rag_block(retrieval: RetrievalResult) -> str:
    """将 RetrievalResult 格式化为 LLM prompt 中的参考文本块"""
    parts = []

    if retrieval.std_clauses:
        parts.append("== 法规标准参考 ==")
        for clause in retrieval.std_clauses[:5]:
            title = clause.get("doc_title", "")
            clause_no = clause.get("clause_no", "")
            text = clause.get("text", "")[:600]
            prefix = f"【{title}】" if title else ""
            if clause_no:
                prefix += f"{clause_no} "
            parts.append(f"{prefix}{text}")

    if retrieval.template_snippets:
        parts.append("\n== 知识库模板片段 ==")
        for snip in retrieval.template_snippets[:3]:
            name = snip.get("chapter_name", "")
            text = snip.get("text", "")[:400]
            parts.append(f"【{name}】{text}")

    if retrieval.bid_cases:
        parts.append("\n== 历史中标案例参考 ==")
        for case in retrieval.bid_cases[:3]:
            name = case.get("chapter_name", "")
            text = case.get("content", "")[:400]
            parts.append(f"【{name}】{text}")

    return "\n".join(parts) if parts else "暂无相关参考资料"


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
) -> str:
    """组装完整的 user prompt"""
    return (
        f"请编写投标文件【{plan.chapter_no} {plan.title}】章节正文。\n\n"
        f"== 招标项目信息 ==\n{project_info}\n\n"
        f"== 投标企业信息 ==\n{enterprise_info}\n\n"
        f"== 本章必须覆盖的关键点 ==\n{_build_key_points_text(plan)}\n\n"
        f"== 建议篇幅 ==\n约 {plan.estimated_words} 字\n\n"
        f"{_build_rag_block(retrieval)}"
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

        prompt = _build_user_prompt(plan, retrieval, project_info, ent_info)

        try:
            content = await _call_llm(prompt)
        except Exception as e:
            logger.error("章节 %s LLM 生成失败: %s", plan.chapter_no, e)
            content = f"（章节生成失败: {e}）"

        sources = _extract_sources(retrieval)

        drafts.append(DraftChapter(
            chapter_no=plan.chapter_no,
            title=plan.title,
            content=content,
            sources_cited=sources,
            word_count=len(content),
        ))

    return drafts
