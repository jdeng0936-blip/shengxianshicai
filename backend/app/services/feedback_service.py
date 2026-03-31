"""
用户反馈服务 — FeedbackLog CRUD + 差异度计算

数据飞轮核心：AI 生成 → 用户修改 → 差异度量化 → 模型微调参考
"""
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import FeedbackLog


def _calc_diff_ratio(original: str, modified: str) -> float:
    """计算编辑差异度（Jaccard距离），返回 0~1"""
    if not original or not modified:
        return 1.0
    set_a = set(original)
    set_b = set(modified)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return round(1.0 - intersection / union, 4)


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
        """提交反馈"""
        diff_ratio = None
        if action == "edit" and modified_text:
            diff_ratio = _calc_diff_ratio(original_text, modified_text)

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
        return log

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
