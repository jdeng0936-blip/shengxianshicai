"""
投标项目 Service — BidProject + TenderRequirement + BidChapter CRUD

Tenant 隔离：所有查询注入 tenant_id 过滤。
"""
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bid_project import BidProject, TenderRequirement, BidChapter
from app.models.enterprise import Enterprise
from app.schemas.bid_project import (
    BidProjectCreate, BidProjectUpdate,
    TenderRequirementCreate, TenderRequirementUpdate,
    BidChapterCreate, BidChapterUpdate,
)


class BidProjectService:
    """投标项目 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ========== BidProject CRUD ==========

    async def list_projects(self, tenant_id: int) -> list[BidProject]:
        result = await self.session.execute(
            select(BidProject)
            .where(BidProject.tenant_id == tenant_id)
            .order_by(BidProject.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_project(self, project_id: int, tenant_id: int) -> Optional[BidProject]:
        result = await self.session.execute(
            select(BidProject)
            .where(BidProject.id == project_id, BidProject.tenant_id == tenant_id)
            .options(
                selectinload(BidProject.requirements),
                selectinload(BidProject.chapters),
                selectinload(BidProject.quotation_sheets),
            )
        )
        return result.scalar_one_or_none()

    async def create_project(
        self, data: BidProjectCreate, tenant_id: int, user_id: int
    ) -> BidProject:
        # 安全: 校验 enterprise_id 是否属于当前租户
        if data.enterprise_id:
            await self._verify_enterprise_ownership(data.enterprise_id, tenant_id)

        project = BidProject(
            tenant_id=tenant_id,
            created_by=user_id,
            **data.model_dump(),
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def update_project(
        self, project_id: int, tenant_id: int, data: BidProjectUpdate
    ) -> Optional[BidProject]:
        project = await self.get_project(project_id, tenant_id)
        if not project:
            return None

        # 安全: 如果更新了 enterprise_id，校验归属
        update_data = data.model_dump(exclude_none=True)
        if "enterprise_id" in update_data and update_data["enterprise_id"]:
            await self._verify_enterprise_ownership(update_data["enterprise_id"], tenant_id)

        for k, v in update_data.items():
            setattr(project, k, v)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def delete_project(self, project_id: int, tenant_id: int) -> bool:
        project = await self.get_project(project_id, tenant_id)
        if not project:
            return False
        await self.session.delete(project)
        await self.session.commit()
        return True

    async def _verify_enterprise_ownership(self, enterprise_id: int, tenant_id: int):
        """安全: 校验 enterprise_id 是否属于当前租户，防止跨租户企业挂载"""
        result = await self.session.execute(
            select(Enterprise.id).where(
                Enterprise.id == enterprise_id,
                Enterprise.tenant_id == tenant_id,
            )
        )
        if not result.scalar_one_or_none():
            raise PermissionError(
                f"企业(id={enterprise_id})不属于当前租户，禁止绑定"
            )

    async def update_status(
        self, project_id: int, tenant_id: int, status: str
    ) -> Optional[BidProject]:
        project = await self.get_project(project_id, tenant_id)
        if not project:
            return None
        project.status = status
        await self.session.commit()
        await self.session.refresh(project)
        return project

    # ========== TenderRequirement CRUD ==========

    async def list_requirements(self, project_id: int, tenant_id: int) -> list[TenderRequirement]:
        # 先校验项目归属
        project = await self.get_project(project_id, tenant_id)
        if not project:
            return []
        result = await self.session.execute(
            select(TenderRequirement)
            .where(TenderRequirement.project_id == project_id)
            .order_by(TenderRequirement.sort_order)
        )
        return list(result.scalars().all())

    async def create_requirement(
        self, project_id: int, tenant_id: int, data: TenderRequirementCreate, user_id: int
    ) -> Optional[TenderRequirement]:
        project = await self.get_project(project_id, tenant_id)
        if not project:
            return None
        req = TenderRequirement(
            project_id=project_id,
            tenant_id=tenant_id,
            created_by=user_id,
            **data.model_dump(),
        )
        self.session.add(req)
        await self.session.commit()
        await self.session.refresh(req)
        return req

    async def batch_create_requirements(
        self, project_id: int, tenant_id: int,
        items: list[TenderRequirementCreate], user_id: int
    ) -> list[TenderRequirement]:
        """批量创建招标要求（招标文件解析后使用）"""
        project = await self.get_project(project_id, tenant_id)
        if not project:
            return []
        reqs = []
        for data in items:
            req = TenderRequirement(
                project_id=project_id,
                tenant_id=tenant_id,
                created_by=user_id,
                **data.model_dump(),
            )
            self.session.add(req)
            reqs.append(req)
        await self.session.commit()
        for r in reqs:
            await self.session.refresh(r)
        return reqs

    async def update_requirement(
        self, req_id: int, tenant_id: int, data: TenderRequirementUpdate
    ) -> Optional[TenderRequirement]:
        result = await self.session.execute(
            select(TenderRequirement)
            .join(BidProject)
            .where(TenderRequirement.id == req_id, BidProject.tenant_id == tenant_id)
        )
        req = result.scalar_one_or_none()
        if not req:
            return None
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(req, k, v)
        await self.session.commit()
        await self.session.refresh(req)
        return req

    async def delete_requirement(self, req_id: int, tenant_id: int) -> bool:
        result = await self.session.execute(
            select(TenderRequirement)
            .join(BidProject)
            .where(TenderRequirement.id == req_id, BidProject.tenant_id == tenant_id)
        )
        req = result.scalar_one_or_none()
        if not req:
            return False
        await self.session.delete(req)
        await self.session.commit()
        return True

    # ========== BidChapter CRUD ==========

    async def list_chapters(self, project_id: int, tenant_id: int) -> list[BidChapter]:
        project = await self.get_project(project_id, tenant_id)
        if not project:
            return []
        result = await self.session.execute(
            select(BidChapter)
            .where(BidChapter.project_id == project_id)
            .order_by(BidChapter.sort_order)
        )
        return list(result.scalars().all())

    async def create_chapter(
        self, project_id: int, tenant_id: int, data: BidChapterCreate, user_id: int
    ) -> Optional[BidChapter]:
        project = await self.get_project(project_id, tenant_id)
        if not project:
            return None
        chapter = BidChapter(
            project_id=project_id,
            tenant_id=tenant_id,
            created_by=user_id,
            **data.model_dump(),
        )
        self.session.add(chapter)
        await self.session.commit()
        await self.session.refresh(chapter)
        return chapter

    async def update_chapter(
        self, chapter_id: int, tenant_id: int, data: BidChapterUpdate
    ) -> Optional[BidChapter]:
        result = await self.session.execute(
            select(BidChapter)
            .join(BidProject)
            .where(BidChapter.id == chapter_id, BidProject.tenant_id == tenant_id)
        )
        chapter = result.scalar_one_or_none()
        if not chapter:
            return None
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(chapter, k, v)
        await self.session.commit()
        await self.session.refresh(chapter)
        return chapter

    async def delete_chapter(self, chapter_id: int, tenant_id: int) -> bool:
        result = await self.session.execute(
            select(BidChapter)
            .join(BidProject)
            .where(BidChapter.id == chapter_id, BidProject.tenant_id == tenant_id)
        )
        chapter = result.scalar_one_or_none()
        if not chapter:
            return False
        await self.session.delete(chapter)
        await self.session.commit()
        return True

    async def get_project_count(self, tenant_id: int) -> int:
        result = await self.session.execute(
            select(func.count(BidProject.id)).where(BidProject.tenant_id == tenant_id)
        )
        return result.scalar() or 0
