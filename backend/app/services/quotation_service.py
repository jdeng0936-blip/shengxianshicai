"""
报价表 Service — QuotationSheet + QuotationItem CRUD

Tenant 隔离：通过 BidProject 间接隔离。
"""
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bid_project import BidProject
from app.models.quotation import QuotationSheet, QuotationItem
from app.schemas.quotation import (
    QuotationSheetCreate, QuotationSheetUpdate,
    QuotationItemCreate, QuotationItemUpdate,
)


class QuotationService:
    """报价表 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _check_project(self, project_id: int, tenant_id: int) -> Optional[BidProject]:
        result = await self.session.execute(
            select(BidProject)
            .where(BidProject.id == project_id, BidProject.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    # ========== QuotationSheet CRUD ==========

    async def list_sheets(self, project_id: int, tenant_id: int) -> list[QuotationSheet]:
        if not await self._check_project(project_id, tenant_id):
            return []
        result = await self.session.execute(
            select(QuotationSheet)
            .where(QuotationSheet.project_id == project_id)
            .options(selectinload(QuotationSheet.items))
            .order_by(QuotationSheet.version.desc())
        )
        return list(result.scalars().all())

    async def get_sheet(self, sheet_id: int, tenant_id: int) -> Optional[QuotationSheet]:
        result = await self.session.execute(
            select(QuotationSheet)
            .join(BidProject)
            .where(QuotationSheet.id == sheet_id, BidProject.tenant_id == tenant_id)
            .options(selectinload(QuotationSheet.items))
        )
        return result.scalar_one_or_none()

    async def create_sheet(
        self, data: QuotationSheetCreate, tenant_id: int, user_id: int
    ) -> Optional[QuotationSheet]:
        if not await self._check_project(data.project_id, tenant_id):
            return None

        # 自动递增版本号
        max_ver = await self.session.execute(
            select(func.coalesce(func.max(QuotationSheet.version), 0))
            .where(
                QuotationSheet.project_id == data.project_id,
                QuotationSheet.tenant_id == tenant_id,  # 安全: 防止跨租户版本号干扰
            )
        )
        next_version = (max_ver.scalar() or 0) + 1

        sheet = QuotationSheet(
            project_id=data.project_id,
            version=next_version,
            discount_rate=data.discount_rate,
            budget_amount=data.budget_amount,
            pricing_method=data.pricing_method,
            remarks=data.remarks,
            tenant_id=tenant_id,
            created_by=user_id,
        )
        self.session.add(sheet)
        await self.session.flush()

        # 创建明细行并计算总金额
        total = 0.0
        for item_data in data.items:
            item = QuotationItem(
                sheet_id=sheet.id,
                tenant_id=tenant_id,
                created_by=user_id,
                **item_data.model_dump(),
            )
            # 自动计算小计
            if item.unit_price and item.quantity and not item.amount:
                item.amount = round(item.unit_price * item.quantity, 2)
            if item.amount:
                total += item.amount
            self.session.add(item)

        sheet.total_amount = round(total, 2) if total > 0 else None
        await self.session.commit()
        await self.session.refresh(sheet)
        return sheet

    async def update_sheet(
        self, sheet_id: int, tenant_id: int, data: QuotationSheetUpdate
    ) -> Optional[QuotationSheet]:
        sheet = await self.get_sheet(sheet_id, tenant_id)
        if not sheet:
            return None
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(sheet, k, v)
        await self.session.commit()
        await self.session.refresh(sheet)
        return sheet

    async def delete_sheet(self, sheet_id: int, tenant_id: int) -> bool:
        sheet = await self.get_sheet(sheet_id, tenant_id)
        if not sheet:
            return False
        await self.session.delete(sheet)
        await self.session.commit()
        return True

    # ========== QuotationItem CRUD ==========

    async def add_item(
        self, sheet_id: int, tenant_id: int, data: QuotationItemCreate, user_id: int
    ) -> Optional[QuotationItem]:
        sheet = await self.get_sheet(sheet_id, tenant_id)
        if not sheet:
            return None
        item = QuotationItem(
            sheet_id=sheet_id,
            tenant_id=tenant_id,
            created_by=user_id,
            **data.model_dump(),
        )
        if item.unit_price and item.quantity and not item.amount:
            item.amount = round(item.unit_price * item.quantity, 2)
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def update_item(
        self, item_id: int, tenant_id: int, data: QuotationItemUpdate
    ) -> Optional[QuotationItem]:
        result = await self.session.execute(
            select(QuotationItem)
            .join(QuotationSheet)
            .join(BidProject)
            .where(QuotationItem.id == item_id, BidProject.tenant_id == tenant_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return None
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(item, k, v)
        # 重算小计
        if item.unit_price and item.quantity:
            item.amount = round(item.unit_price * item.quantity, 2)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def delete_item(self, item_id: int, tenant_id: int) -> bool:
        result = await self.session.execute(
            select(QuotationItem)
            .join(QuotationSheet)
            .join(BidProject)
            .where(QuotationItem.id == item_id, BidProject.tenant_id == tenant_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return False
        await self.session.delete(item)
        await self.session.commit()
        return True

    async def recalculate_total(self, sheet_id: int, tenant_id: int) -> Optional[QuotationSheet]:
        """重新计算报价表总金额，并回写到 BidProject.bid_amount"""
        sheet = await self.get_sheet(sheet_id, tenant_id)
        if not sheet:
            return None
        total = sum(item.amount or 0 for item in sheet.items)
        sheet.total_amount = round(total, 2)

        # 回写项目报价金额
        project = await self._check_project(sheet.project_id, tenant_id)
        if project:
            project.bid_amount = sheet.total_amount

        await self.session.commit()
        await self.session.refresh(sheet)
        return sheet
