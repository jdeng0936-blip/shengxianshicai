"""
向量嵌入服务 — Gemini text-embedding-004 + pgvector 语义检索

功能:
  1. embed_text — 单文本向量化
  2. embed_batch — 批量向量化
  3. search_similar — 语义相似检索（余弦距离）

依赖: google-genai, sqlalchemy, pgvector
"""
import os
from typing import Optional

from google import genai
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ========== 配置 ==========
EMBED_MODEL = "gemini-embedding-001"
DIMENSION = 1536


class EmbeddingService:
    """向量嵌入服务"""

    def __init__(self, session: AsyncSession):
        self.session = session
        api_key = os.getenv("GEMINI_API_KEY", "")
        self._client = genai.Client(api_key=api_key) if api_key else None

    async def embed_text(self, content: str) -> Optional[list[float]]:
        """单文本向量化 — 返回 1536 维向量"""
        if not self._client:
            return None
        try:
            result = self._client.models.embed_content(
                model=EMBED_MODEL,
                contents=[content],
                config={"output_dimensionality": DIMENSION},
            )
            return result.embeddings[0].values
        except Exception as e:
            print(f"⚠️ 向量化失败: {e}")
            return None

    async def embed_batch(self, texts: list[str]) -> list[Optional[list[float]]]:
        """批量文本向量化"""
        if not self._client:
            return [None] * len(texts)
        try:
            result = self._client.models.embed_content(
                model=EMBED_MODEL,
                contents=texts,
                config={"output_dimensionality": DIMENSION},
            )
            return [e.values for e in result.embeddings]
        except Exception as e:
            print(f"⚠️ 批量向量化失败: {e}")
            return [None] * len(texts)

    async def search_similar(
        self,
        query: str,
        tenant_id: int,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> list[dict]:
        """
        语义相似检索 — 基于 pgvector 余弦距离，多租户强隔离
        
        Args:
            query: 查询文本
            tenant_id: 租户ID（0 代表通用基础库）
            top_k: 返回前 K 条
            threshold: 余弦距离阈值（越小越相似）

        Returns:
            [{"clause_id", "clause_no", "content", "doc_title", "distance"}, ...]
        """
        # 先对查询文本向量化
        query_emb = await self.embed_text(query)
        if query_emb is None:
            return []

        emb_str = "[" + ",".join(str(v) for v in query_emb) + "]"

        # pgvector 余弦距离检索（<=> 运算符），强制租户隔离
        sql = text("""
            SELECT
                c.id AS clause_id,
                c.clause_no,
                c.content,
                d.title AS doc_title,
                (c.embedding <=> :query_emb::vector) AS distance
            FROM std_clause c
            JOIN std_document d ON c.document_id = d.id
            WHERE c.embedding IS NOT NULL 
              AND (d.tenant_id = :tenant_id OR d.tenant_id = 0)
            ORDER BY c.embedding <=> :query_emb::vector
            LIMIT :top_k
        """)

        result = await self.session.execute(sql, {
            "query_emb": emb_str,
            "top_k": top_k,
            "tenant_id": tenant_id,
        })
        rows = result.fetchall()

        # 过滤掉距离超过阈值的结果
        return [
            {
                "clause_id": row.clause_id,
                "clause_no": row.clause_no,
                "content": row.content,
                "doc_title": row.doc_title,
                "distance": round(float(row.distance), 4),
            }
            for row in rows
            if float(row.distance) <= threshold
        ]
