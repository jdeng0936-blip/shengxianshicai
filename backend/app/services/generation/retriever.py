"""
Node 2: RAG 三层检索 — 为每个章节检索相关法规、模板片段、历史案例

复用 HybridRetriever + EmbeddingService，按章节计划分批并发检索。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from app.services.generation.planner import ChapterPlan

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """单章节的检索结果"""
    chapter_no: str
    std_clauses: list[dict] = field(default_factory=list)
    template_snippets: list[dict] = field(default_factory=list)
    bid_cases: list[dict] = field(default_factory=list)
    table_data: list[dict] = field(default_factory=list)


def _build_query(plan: ChapterPlan) -> str:
    """从章节计划构建检索 query"""
    parts = [plan.title]
    # 取前 3 个关键点拼接，避免 query 过长影响检索质量
    for kp in plan.key_points[:3]:
        parts.append(kp)
    return " ".join(parts)


async def _retrieve_single_chapter(
    session: AsyncSession,
    tenant_id: int,
    plan: ChapterPlan,
    top_k: int,
) -> RetrievalResult:
    """单章节检索：调用 HybridRetriever 获取三层结果"""
    from app.services.retriever import HybridRetriever

    query = _build_query(plan)
    retriever = HybridRetriever(session=session, tenant_id=tenant_id)

    try:
        raw = await retriever.retrieve(
            query=query,
            context={"chapter_no": plan.chapter_no, "title": plan.title},
            top_k=top_k,
        )
    except Exception as e:
        logger.warning("章节 %s 检索失败: %s", plan.chapter_no, e)
        return RetrievalResult(chapter_no=plan.chapter_no)

    # 将 HybridRetriever 的扁平结果拆分为三类
    std_clauses = []
    template_snippets = []
    table_data = []

    for item in raw.get("merged", []):
        item_type = item.get("type", "")
        content = item.get("content", {})
        if item_type == "semantic":
            std_clauses.append(content)
        elif item_type == "snippet":
            template_snippets.append(content)
        elif item_type == "table":
            table_data.append(content)

    # snippet_results 直接作为 bid_cases（历史案例/知识库片段）
    bid_cases = raw.get("snippet_results", [])

    return RetrievalResult(
        chapter_no=plan.chapter_no,
        std_clauses=std_clauses,
        template_snippets=template_snippets,
        bid_cases=bid_cases,
        table_data=table_data,
    )


@dataclass
class EnterpriseContext:
    """从 DB 加载的企业结构化数据（高风险字段，不可由 LLM 编造）"""
    enterprise_name: str = ""
    cold_chain_vehicles: int = 0
    warehouse_area: float = 0.0
    employee_count: int = 0
    credential_list: list[dict] = field(default_factory=list)
    # 格式: [{"type": "food_license", "name": "食品经营许可证", "cert_no": "...", "valid_until": "..."}]

    def to_prompt_block(self) -> str:
        """构建带不可篡改约束的 prompt 文本块"""
        lines = [
            "== 投标企业结构化数据（以下数值从企业数据库提取，严禁修改或编造） ==",
            f"企业名称: {self.enterprise_name}",
            f"冷链运输车辆数: {self.cold_chain_vehicles} 辆",
        ]
        if self.warehouse_area > 0:
            lines.append(f"仓储面积: {self.warehouse_area} 平方米")
        if self.employee_count > 0:
            lines.append(f"员工人数: {self.employee_count} 人")
        if self.credential_list:
            lines.append("持有资质证书:")
            for cred in self.credential_list:
                name = cred.get("name", "")
                cert_no = cred.get("cert_no", "")
                valid = cred.get("valid_until", "")
                line = f"  - {name}"
                if cert_no:
                    line += f"（编号: {cert_no}）"
                if valid:
                    line += f"（有效期至: {valid}）"
                lines.append(line)
        lines.append("⚠️ 以上数据为确定值，正文中引用时必须保持一致，不得自行编造或修改数字。")
        return "\n".join(lines)

    def to_validation_dict(self) -> dict:
        """返回用于后置校验的关键字段字典"""
        d: dict = {"enterprise_name": self.enterprise_name}
        if self.cold_chain_vehicles > 0:
            d["cold_chain_vehicles"] = self.cold_chain_vehicles
        if self.warehouse_area > 0:
            d["warehouse_area"] = self.warehouse_area
        if self.employee_count > 0:
            d["employee_count"] = self.employee_count
        for cred in self.credential_list:
            if cred.get("cert_no"):
                d[f"cert_{cred['type']}"] = cred["cert_no"]
        return d


async def fetch_enterprise_context(
    session: AsyncSession,
    tenant_id: int,
    enterprise_id: int,
) -> EnterpriseContext:
    """从 DB 加载企业 + 资质结构化数据（高风险字段注入源）

    Args:
        session: 数据库会话
        tenant_id: 租户 ID
        enterprise_id: 关联企业 ID

    Returns:
        EnterpriseContext 含企业名、车辆数、资质列表等
    """
    from sqlalchemy import select

    ctx = EnterpriseContext()

    try:
        from app.models.enterprise import Enterprise
        result = await session.execute(
            select(Enterprise).where(
                Enterprise.id == enterprise_id,
                Enterprise.tenant_id == tenant_id,
            )
        )
        ent = result.scalar_one_or_none()
        if ent:
            ctx.enterprise_name = getattr(ent, "name", "") or ""
            ctx.cold_chain_vehicles = getattr(ent, "cold_chain_vehicles", 0) or 0
            ctx.warehouse_area = getattr(ent, "warehouse_area", 0.0) or 0.0
            ctx.employee_count = getattr(ent, "employee_count", 0) or 0
    except Exception as e:
        logger.warning("加载企业数据失败: %s", e)

    try:
        from app.models.credential import Credential
        cred_result = await session.execute(
            select(Credential).where(
                Credential.tenant_id == tenant_id,
            )
        )
        creds = cred_result.scalars().all()
        for c in creds:
            ctx.credential_list.append({
                "type": getattr(c, "cred_type", "") or "",
                "name": getattr(c, "name", "") or "",
                "cert_no": getattr(c, "cert_no", "") or "",
                "valid_until": str(getattr(c, "valid_until", "")) if getattr(c, "valid_until", None) else "",
            })
    except Exception as e:
        logger.warning("加载资质数据失败: %s", e)

    return ctx


async def retrieve_context(
    session: AsyncSession,
    tenant_id: int,
    chapter_plans: list[ChapterPlan],
    project_id: int,
    top_k: int = 5,
) -> list[RetrievalResult]:
    """
    RAG 检索节点

    对每个章节计划，并发执行三层检索:
      L1 — pgvector 语义检索（法规 + 知识库）
      L2 — 结构化参数表查询（报价、资质、企业信息）
      L3 — 结果融合 + Re-rank

    Args:
        session: 数据库会话
        tenant_id: 租户 ID（隔离红线）
        chapter_plans: Node 1 输出的章节计划
        project_id: 项目 ID，用于关联查询报价/资质
        top_k: 每层检索返回条数

    Returns:
        每个章节对应的检索结果列表，顺序与 chapter_plans 一致
    """
    tasks = [
        _retrieve_single_chapter(session, tenant_id, plan, top_k)
        for plan in chapter_plans
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    final = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error("章节 %s 检索异常: %s", chapter_plans[i].chapter_no, r)
            final.append(RetrievalResult(chapter_no=chapter_plans[i].chapter_no))
        else:
            final.append(r)

    return final
