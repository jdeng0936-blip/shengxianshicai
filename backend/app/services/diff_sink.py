"""
差异度下沉服务 — 数据飞轮增强

架构铁律：
  - 用户修改 AI 生成内容后，计算差异度
  - 超过 10% 阈值 → 异步下沉修订文本到 pgvector 知识库
  - 下沉文本标记 source_tag="human_revised", data_density="high"
  - 不阻塞主请求（asyncio.create_task）
  - 测试中严禁调真实 embedding API（必须 Mock）
"""
import asyncio
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

# 差异度阈值：超过此值才触发下沉
DIFF_THRESHOLD = 0.10


def calc_diff_ratio(original: str, revised: str) -> float:
    """
    计算编辑前后的差异度 — Jaccard 距离 × 0.7 + 长度差异 × 0.3

    返回 0.0 ~ 1.0 的浮点数，值越大差异越大。
    """
    if not original or not revised:
        return 1.0
    if original == revised:
        return 0.0

    # Jaccard 距离（基于字级别）
    set_a = set(original)
    set_b = set(revised)
    intersection = set_a & set_b
    union = set_a | set_b
    jaccard = 1.0 - (len(intersection) / len(union)) if union else 1.0

    # 长度差异
    max_len = max(len(original), len(revised))
    length_diff = abs(len(original) - len(revised)) / max_len if max_len else 0.0

    return round(0.7 * jaccard + 0.3 * length_diff, 4)


async def _do_sink(
    revised_text: str,
    chapter_no: str,
    chapter_title: str,
    project_id: int,
    tenant_id: int,
    diff_ratio: float,
) -> None:
    """
    实际执行下沉操作 — 在独立 session 中完成

    1. 调用 EmbeddingService 将修订文本向量化
    2. 写入 knowledge_sink 表（如不存在则 graceful 跳过）
    """
    try:
        async with async_session_factory() as session:
            emb_svc = EmbeddingService(session)
            embedding = await emb_svc.embed_text(revised_text)

            if embedding is None:
                logger.warning("差异度下沉: embedding 生成失败，跳过下沉")
                return

            emb_str = "[" + ",".join(str(v) for v in embedding) + "]"

            # 尝试写入 knowledge_sink 表
            # 如果表不存在，graceful 降级记录日志
            try:
                await session.execute(
                    text("""
                        INSERT INTO knowledge_sink
                            (content, embedding, source_tag, data_density,
                             chapter_no, chapter_title, project_id,
                             tenant_id, diff_ratio)
                        VALUES
                            (:content, :embedding::vector, :source_tag, :data_density,
                             :chapter_no, :chapter_title, :project_id,
                             :tenant_id, :diff_ratio)
                    """),
                    {
                        "content": revised_text,
                        "embedding": emb_str,
                        "source_tag": "human_revised",
                        "data_density": "high",
                        "chapter_no": chapter_no,
                        "chapter_title": chapter_title,
                        "project_id": project_id,
                        "tenant_id": tenant_id,
                        "diff_ratio": diff_ratio,
                    },
                )
                await session.commit()
                logger.info(
                    f"✅ 差异度下沉成功: project={project_id} "
                    f"chapter={chapter_no} diff={diff_ratio}"
                )
            except Exception as db_err:
                logger.warning(f"差异度下沉: 数据库写入失败（表可能不存在）: {db_err}")
                await session.rollback()

    except Exception as e:
        logger.error(f"差异度下沉异常: {e}")


def trigger_sink_if_needed(
    original_text: str,
    revised_text: str,
    chapter_no: str,
    chapter_title: str,
    project_id: int,
    tenant_id: int,
) -> Optional[float]:
    """
    计算差异度，超阈值则异步触发下沉。

    返回差异度值（方便写入 feedback 记录）。
    不阻塞主请求。
    """
    diff_ratio = calc_diff_ratio(original_text, revised_text)

    if diff_ratio > DIFF_THRESHOLD:
        asyncio.create_task(
            _do_sink(
                revised_text=revised_text,
                chapter_no=chapter_no,
                chapter_title=chapter_title,
                project_id=project_id,
                tenant_id=tenant_id,
                diff_ratio=diff_ratio,
            )
        )
        logger.info(f"🔄 差异度 {diff_ratio} > {DIFF_THRESHOLD}，已触发异步下沉")

    return diff_ratio
