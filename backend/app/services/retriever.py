"""
RAG 三层融合检索器

架构:
  L1 — pgvector 语义检索（EmbeddingService.search_similar）
  L2 — 结构化参数表精确查询（TableQueryService.query）
  L3 — 结果融合 + 按相关性 Re-rank

调用方式:
  retriever = HybridRetriever(session)
  results = await retriever.retrieve(query, context)
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding_service import EmbeddingService
from app.services.table_query_service import TableQueryService


class HybridRetriever:
    """三层融合检索器"""

    def __init__(self, session: AsyncSession, tenant_id: int):
        self.session = session
        self.tenant_id = tenant_id
        self.embedding_svc = EmbeddingService(session)
        self.table_svc = TableQueryService()

    async def retrieve(
        self,
        query: str,
        context: Optional[dict] = None,
        top_k: int = 5,
    ) -> dict:
        """
        融合检索入口

        Args:
            query: 用户自然语言查询
            context: 上下文参数（围岩级别、瓦斯等级等），用于 L2 查表
            top_k: L1 语义检索返回条数

        Returns:
            {
                "semantic_results": [...],   # L1 语义检索结果
                "table_results": [...],      # L2 结构化查表结果
                "merged": [...],             # L3 融合排序后的结果
                "summary": "..."             # 检索摘要
            }
        """
        context = context or {}

        # ===== L1: 语义检索 =====
        semantic_results = await self.embedding_svc.search_similar(
            query=query, tenant_id=self.tenant_id, top_k=top_k
        )

        # ===== L2: 结构化查表 =====
        table_results = []
        # 架构升级优化规则 #4：查表意图完全转交由 LLM Tool Calling (ai_router) 判断处理
        # 移除此处的 if-else 硬编码查表逻辑，使 Retriver 更加纯粹聚焦语义检索

        # ===== L3: 融合 + Re-rank =====
        merged = self._merge_and_rank(semantic_results, table_results)

        # 生成检索摘要
        summary = self._build_summary(semantic_results, table_results)

        return {
            "semantic_results": semantic_results,
            "table_results": table_results,
            "merged": merged,
            "summary": summary,
        }

    def _merge_and_rank(
        self, semantic: list[dict], tables: list[dict]
    ) -> list[dict]:
        """
        融合排序逻辑:
          1. 结构化查表结果优先（精确匹配，置信度高）
          2. 语义检索结果按距离排序（距离越小越相关）
          3. 每条结果附带 source 类型标签
        """
        merged = []

        # 结构化结果放前面（权重更高）
        for item in tables:
            merged.append({
                "type": "table",
                "relevance": 1.0,  # 精确匹配满分
                "content": item,
            })

        # 语义结果按余弦距离转换为相关性分数
        for item in semantic:
            distance = item.get("distance", 1.0)
            relevance = max(0, 1.0 - distance)  # 余弦距离 → 相关性
            merged.append({
                "type": "semantic",
                "relevance": round(relevance, 4),
                "content": {
                    "clause_no": item.get("clause_no", ""),
                    "doc_title": item.get("doc_title", ""),
                    "text": item.get("content", ""),
                    "distance": distance,
                },
            })

        # 按相关性降序
        merged.sort(key=lambda x: x["relevance"], reverse=True)

        return merged

    def _build_summary(
        self, semantic: list[dict], tables: list[dict]
    ) -> str:
        """生成检索摘要供 LLM 参考"""
        parts = []
        if tables:
            table_names = [t.get("table", "未知表") for t in tables]
            parts.append(f"结构化查表命中 {len(tables)} 条: {', '.join(table_names)}")
        if semantic:
            parts.append(f"语义检索命中 {len(semantic)} 条标准条款")
        if not parts:
            return "未检索到相关信息"
        return "；".join(parts)
