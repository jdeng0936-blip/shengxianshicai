"""
知识库 Service — 工程案例 + 文档模板 + 章节片段 CRUD

Tenant 隔离：所有查询注入 tenant_id 过滤
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.standard import EngCase
from app.models.document import DocTemplate, ChapterSnippet
from app.schemas.knowledge import (
    EngCaseCreate, EngCaseUpdate,
    DocTemplateCreate,
    ChapterSnippetCreate, ChapterSnippetUpdate,
)


class KnowledgeService:
    """知识库统一服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ========== DAT-02 工程案例 ==========

    async def list_cases(self, tenant_id: int) -> list[EngCase]:
        result = await self.session.execute(
            select(EngCase)
            .where(EngCase.tenant_id == tenant_id)
            .order_by(EngCase.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_case(self, data: EngCaseCreate, tenant_id: int, user_id: int) -> EngCase:
        case = EngCase(
            **data.model_dump(exclude_none=True),
            tenant_id=tenant_id, created_by=user_id,
        )
        self.session.add(case)
        await self.session.flush()
        await self.session.refresh(case)
        return case

    async def update_case(self, case_id: int, tenant_id: int, data: EngCaseUpdate) -> Optional[EngCase]:
        result = await self.session.execute(
            select(EngCase).where(EngCase.id == case_id, EngCase.tenant_id == tenant_id)
        )
        case = result.scalar_one_or_none()
        if not case:
            return None
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(case, k, v)
        await self.session.flush()
        await self.session.refresh(case)
        return case

    async def delete_case(self, case_id: int, tenant_id: int) -> bool:
        result = await self.session.execute(
            select(EngCase).where(EngCase.id == case_id, EngCase.tenant_id == tenant_id)
        )
        case = result.scalar_one_or_none()
        if not case:
            return False
        await self.session.delete(case)
        await self.session.flush()
        return True

    # ========== DAT-03 文档模板 ==========

    async def list_templates(self, tenant_id: int) -> list[DocTemplate]:
        result = await self.session.execute(
            select(DocTemplate)
            .where(DocTemplate.tenant_id == tenant_id)
            .order_by(DocTemplate.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_template(self, data: DocTemplateCreate, tenant_id: int, user_id: int) -> DocTemplate:
        tpl = DocTemplate(
            **data.model_dump(), tenant_id=tenant_id, created_by=user_id,
        )
        self.session.add(tpl)
        await self.session.flush()
        await self.session.refresh(tpl)
        return tpl

    async def delete_template(self, tpl_id: int, tenant_id: int) -> bool:
        result = await self.session.execute(
            select(DocTemplate).where(DocTemplate.id == tpl_id, DocTemplate.tenant_id == tenant_id)
        )
        tpl = result.scalar_one_or_none()
        if not tpl:
            return False
        await self.session.delete(tpl)
        await self.session.flush()
        return True

    # ========== DAT-04 章节片段 ==========

    async def list_snippets(self, tenant_id: int) -> list[ChapterSnippet]:
        result = await self.session.execute(
            select(ChapterSnippet)
            .where(ChapterSnippet.tenant_id == tenant_id)
            .order_by(ChapterSnippet.sort_order, ChapterSnippet.chapter_no)
        )
        return list(result.scalars().all())

    async def create_snippet(self, data: ChapterSnippetCreate, tenant_id: int, user_id: int) -> ChapterSnippet:
        snippet = ChapterSnippet(
            **data.model_dump(), tenant_id=tenant_id, created_by=user_id,
        )
        self.session.add(snippet)
        await self.session.flush()
        await self.session.refresh(snippet)
        return snippet

    async def update_snippet(self, snp_id: int, tenant_id: int, data: ChapterSnippetUpdate) -> Optional[ChapterSnippet]:
        result = await self.session.execute(
            select(ChapterSnippet).where(ChapterSnippet.id == snp_id, ChapterSnippet.tenant_id == tenant_id)
        )
        snippet = result.scalar_one_or_none()
        if not snippet:
            return None
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(snippet, k, v)
        await self.session.flush()
        await self.session.refresh(snippet)
        return snippet

    async def delete_snippet(self, snp_id: int, tenant_id: int) -> bool:
        result = await self.session.execute(
            select(ChapterSnippet).where(ChapterSnippet.id == snp_id, ChapterSnippet.tenant_id == tenant_id)
        )
        snippet = result.scalar_one_or_none()
        if not snippet:
            return False
        await self.session.delete(snippet)
        await self.session.flush()
        return True
