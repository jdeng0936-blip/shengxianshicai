"""
用户反馈服务 — FeedbackLog CRUD + 差异度计算 + 数据飞轮

数据飞轮核心：AI 生成 → 用户修改 → 差异度量化 → 高质量语料回灌 pgvector
"""
import asyncio
import difflib
import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import FeedbackLog

logger = logging.getLogger("feedback_service")

# 实质性修改阈值：修改超过 10% 才触发飞轮下沉
_DIFF_THRESHOLD = 0.10
# 过短文本不值得作为训练语料
_MIN_TEXT_LENGTH = 50


def _calc_diff_ratio(original: str, modified: str) -> float:
    """计算编辑差异度（SequenceMatcher 序列对齐），返回 0~1

    相比 Jaccard 距离（字符集合），SequenceMatcher 基于最长公共子序列，
    对长文本的段落增删、语句调序等编辑操作的度量更精确。
    """
    if original == modified:
        return 0.0
    if not original or not modified:
        return 1.0
    similarity = difflib.SequenceMatcher(None, original, modified).ratio()
    return round(1.0 - similarity, 4)


class FeedbackService:
    """用户反馈服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def submit_feedback(
        self,
        project_id: int,
        chapter_no: str,
        chapter_title: str,
        original_text: str,
        action: str,
        tenant_id: int,
        user_id: int,
        modified_text: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> FeedbackLog:
        """提交反馈，当编辑差异超过阈值时触发飞轮数据下沉"""
        diff_ratio = None
        flywheel_triggered = False

        if action == "edit" and modified_text:
            diff_ratio = _calc_diff_ratio(original_text, modified_text)

            # 飞轮触发：实质性修改 + 文本足够长 → 异步下沉到 pgvector
            if (
                diff_ratio is not None
                and diff_ratio > _DIFF_THRESHOLD
                and len(modified_text) > _MIN_TEXT_LENGTH
            ):
                flywheel_triggered = True
                logger.info(
                    f"[数据飞轮] diff={diff_ratio:.1%} 超过阈值，"
                    f"触发异步下沉 | chapter={chapter_title[:20]}"
                )
                asyncio.create_task(
                    self._async_sink_to_knowledge_base(
                        chapter_title=chapter_title,
                        golden_text=modified_text,
                        original_text=original_text,
                        diff_ratio=diff_ratio,
                        tenant_id=tenant_id,
                    )
                )

        log = FeedbackLog(
            project_id=project_id,
            chapter_no=chapter_no,
            chapter_title=chapter_title,
            original_text=original_text,
            modified_text=modified_text,
            action=action,
            comment=comment,
            diff_ratio=diff_ratio,
            tenant_id=tenant_id,
            created_by=user_id,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)

        # 回写 BidChapter.edit_ratio（闭环数据飞轮）
        if diff_ratio is not None:
            await self._update_chapter_edit_ratio(
                project_id, chapter_no, diff_ratio
            )

        return log

    async def _update_chapter_edit_ratio(
        self, project_id: int, chapter_no: str, diff_ratio: float
    ) -> None:
        """将最新 diff_ratio 回写到 BidChapter.edit_ratio，闭合数据飞轮链路"""
        try:
            from app.models.bid_project import BidChapter
            result = await self.session.execute(
                select(BidChapter).where(
                    BidChapter.project_id == project_id,
                    BidChapter.chapter_no == chapter_no,
                )
            )
            chapter = result.scalar_one_or_none()
            if chapter:
                chapter.edit_ratio = diff_ratio
                await self.session.commit()
                logger.info(
                    f"[edit_ratio回写] project={project_id} chapter={chapter_no} "
                    f"edit_ratio={diff_ratio:.2%}"
                )
        except Exception as e:
            logger.warning(f"[edit_ratio回写] 失败（不阻塞主流程）: {e}")

    @staticmethod
    async def _async_sink_to_knowledge_base(
        chapter_title: str,
        golden_text: str,
        original_text: str,
        diff_ratio: float,
        tenant_id: int,
    ):
        """将人工修订过的高质量语料异步向量化入 pgvector，供后续 RAG 检索"""
        try:
            from app.core.database import async_session_factory
            from app.services.embedding_service import EmbeddingService
            from sqlalchemy import text as sql_text

            async with async_session_factory() as session:
                emb_svc = EmbeddingService(session)
                embedding = await emb_svc.embed_text(golden_text[:2000])
                if embedding is None:
                    logger.warning("[数据飞轮] 向量化失败，跳过下沉")
                    return

                emb_str = "[" + ",".join(str(v) for v in embedding) + "]"
                await session.execute(
                    sql_text("""
                        INSERT INTO chapter_snippet
                            (chapter_no, chapter_name, content, embedding, tenant_id)
                        VALUES
                            (:chapter_no, :chapter_name, :content,
                             CAST(:embedding AS vector), :tenant_id)
                    """),
                    {
                        "chapter_no": "flywheel",
                        "chapter_name": chapter_title,
                        "content": golden_text,
                        "embedding": emb_str,
                        "tenant_id": tenant_id,
                    },
                )
                await session.commit()

            logger.info(
                f"[数据飞轮] 人工修订片段已下沉 | "
                f"chapter={chapter_title[:20]} | diff={diff_ratio:.1%}"
            )
        except Exception as e:
            logger.error(f"[数据飞轮] 下沉失败: {e}", exc_info=True)

    async def list_feedback(
        self, tenant_id: int, project_id: Optional[int] = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[FeedbackLog], int]:
        """查询反馈列表"""
        q = select(FeedbackLog).where(FeedbackLog.tenant_id == tenant_id)
        if project_id:
            q = q.where(FeedbackLog.project_id == project_id)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await self.session.execute(count_q)).scalar() or 0

        q = q.order_by(FeedbackLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.session.execute(q)).scalars().all()
        return list(rows), total

    async def get_stats(self, tenant_id: int, project_id: Optional[int] = None) -> dict:
        """反馈统计"""
        q = select(FeedbackLog.action, func.count()).where(
            FeedbackLog.tenant_id == tenant_id
        )
        if project_id:
            q = q.where(FeedbackLog.project_id == project_id)
        q = q.group_by(FeedbackLog.action)

        result = await self.session.execute(q)
        counts = {row[0]: row[1] for row in result.fetchall()}

        # 平均编辑差异度
        avg_q = select(func.avg(FeedbackLog.diff_ratio)).where(
            FeedbackLog.tenant_id == tenant_id,
            FeedbackLog.action == "edit",
            FeedbackLog.diff_ratio.isnot(None),
        )
        if project_id:
            avg_q = avg_q.where(FeedbackLog.project_id == project_id)
        avg_diff = (await self.session.execute(avg_q)).scalar()

        return {
            "accept": counts.get("accept", 0),
            "edit": counts.get("edit", 0),
            "reject": counts.get("reject", 0),
            "total": sum(counts.values()),
            "avg_diff_ratio": round(float(avg_diff), 4) if avg_diff else None,
        }
