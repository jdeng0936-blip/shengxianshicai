"""
商机公告 CRUD 服务 — tenant_id 强制隔离
"""
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tender_notice import TenderNotice
from app.schemas.tender_notice import TenderNoticeCreate, TenderNoticeUpdate


class TenderNoticeService:
    """商机公告 CRUD"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_notices(
        self, tenant_id: int,
        status: Optional[str] = None,
        match_level: Optional[str] = None,
        page: int = 1, page_size: int = 20,
    ) -> tuple[list[TenderNotice], int]:
        q = select(TenderNotice).where(TenderNotice.tenant_id == tenant_id)
        if status:
            q = q.where(TenderNotice.status == status)
        if match_level:
            q = q.where(TenderNotice.match_level == match_level)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await self.session.execute(count_q)).scalar() or 0

        q = q.order_by(TenderNotice.id.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.session.execute(q)).scalars().all()
        return list(rows), total

    async def get_notice(self, notice_id: int, tenant_id: int) -> Optional[TenderNotice]:
        result = await self.session.execute(
            select(TenderNotice).where(
                TenderNotice.id == notice_id,
                TenderNotice.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_notice(self, data: TenderNoticeCreate, tenant_id: int, user_id: int) -> TenderNotice:
        notice = TenderNotice(
            tenant_id=tenant_id,
            created_by=user_id,
            status="new",
            **data.model_dump(),
        )
        self.session.add(notice)
        await self.session.commit()
        await self.session.refresh(notice)
        return notice

    async def update_notice(self, notice_id: int, tenant_id: int, data: TenderNoticeUpdate) -> Optional[TenderNotice]:
        notice = await self.get_notice(notice_id, tenant_id)
        if not notice:
            return None
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(notice, k, v)
        await self.session.commit()
        await self.session.refresh(notice)
        return notice

    async def delete_notice(self, notice_id: int, tenant_id: int) -> bool:
        notice = await self.get_notice(notice_id, tenant_id)
        if not notice:
            return False
        await self.session.delete(notice)
        await self.session.commit()
        return True

    async def get_stats(self, tenant_id: int) -> dict:
        base = select(TenderNotice).where(TenderNotice.tenant_id == tenant_id)

        total = (await self.session.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar() or 0

        new_count = (await self.session.execute(
            select(func.count()).where(
                TenderNotice.tenant_id == tenant_id,
                TenderNotice.status == "new",
            )
        )).scalar() or 0

        recommended = (await self.session.execute(
            select(func.count()).where(
                TenderNotice.tenant_id == tenant_id,
                TenderNotice.status == "recommended",
            )
        )).scalar() or 0

        risky = (await self.session.execute(
            select(func.count()).where(
                TenderNotice.tenant_id == tenant_id,
                TenderNotice.match_level == "risky",
            )
        )).scalar() or 0

        converted = (await self.session.execute(
            select(func.count()).where(
                TenderNotice.tenant_id == tenant_id,
                TenderNotice.status == "converted",
            )
        )).scalar() or 0

        avg_score = (await self.session.execute(
            select(func.avg(TenderNotice.match_score)).where(
                TenderNotice.tenant_id == tenant_id,
                TenderNotice.match_score.isnot(None),
            )
        )).scalar()

        return {
            "total": total,
            "new_count": new_count,
            "recommended": recommended,
            "risky": risky,
            "converted": converted,
            "avg_match_score": round(float(avg_score), 1) if avg_score else None,
        }
