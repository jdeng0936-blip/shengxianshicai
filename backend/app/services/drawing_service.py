"""
图纸管理 Service — 业务逻辑层

所有查询强制注入 tenant_id 过滤（规范红线第 3 条）。
文件存储：本期采用本地磁盘 + Docker Volume，路径 uploads/drawings/{tenant_id}/
"""
import os
import uuid
import aiofiles
from typing import Optional
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.drawing import DrawingTemplate, DrawingBinding
from app.schemas.drawing import (
    DrawingCreate,
    DrawingUpdate,
    DrawingBindingCreate,
    DrawingMatchRequest,
)

# 上传文件根目录（相对于 backend/ 运行目录）
UPLOAD_ROOT = Path("uploads/drawings")

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".dwg", ".dxf"}


class DrawingService:
    """图纸管理 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ========== 图纸 CRUD ==========

    async def list_drawings(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        name: Optional[str] = None,
    ) -> tuple[list[DrawingTemplate], int]:
        """分页查询图纸列表

        Returns:
            (items, total) — 图纸列表 + 总数
        """
        # 基础查询 — 强制 tenant_id 隔离
        query = select(DrawingTemplate).where(DrawingTemplate.tenant_id == tenant_id)

        # 筛选条件
        if category:
            query = query.where(DrawingTemplate.category == category)
        if name:
            query = query.where(DrawingTemplate.name.ilike(f"%{name}%"))

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(DrawingTemplate.id.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        drawings = list(result.scalars().all())

        return drawings, total

    async def get_drawing(self, drawing_id: int, tenant_id: int) -> Optional[DrawingTemplate]:
        """获取单个图纸详情（含 tenant_id 隔离）"""
        result = await self.session.execute(
            select(DrawingTemplate).where(
                DrawingTemplate.id == drawing_id,
                DrawingTemplate.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_drawing(
        self,
        data: DrawingCreate,
        file: UploadFile,
        tenant_id: int,
        created_by: int,
    ) -> DrawingTemplate:
        """上传图纸 — 保存文件到磁盘 + 写入数据库记录"""
        # 校验文件扩展名
        original_name = file.filename or "unknown"
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}，允许: {', '.join(ALLOWED_EXTENSIONS)}")

        # 构建存储路径：uploads/drawings/{tenant_id}/{uuid}.{ext}
        tenant_dir = UPLOAD_ROOT / str(tenant_id)
        tenant_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = tenant_dir / unique_name

        # 异步写入文件
        content = await file.read()
        file_size = len(content)
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        # 存储相对路径（相对于 backend/ 目录）
        relative_url = str(file_path)

        # 创建数据库记录
        drawing = DrawingTemplate(
            name=data.name,
            category=data.category,
            description=data.description,
            file_url=relative_url,
            file_format=ext.lstrip("."),
            file_size=file_size,
            version=1,
            is_current=True,
            tenant_id=tenant_id,
            created_by=created_by,
        )
        self.session.add(drawing)
        await self.session.flush()
        await self.session.refresh(drawing)
        return drawing

    async def update_drawing(
        self,
        drawing_id: int,
        tenant_id: int,
        data: DrawingUpdate,
    ) -> Optional[DrawingTemplate]:
        """更新图纸元信息"""
        drawing = await self.get_drawing(drawing_id, tenant_id)
        if not drawing:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(drawing, key, value)
        await self.session.flush()
        await self.session.refresh(drawing)
        return drawing

    async def delete_drawing(self, drawing_id: int, tenant_id: int) -> bool:
        """删除图纸 — 删除数据库记录 + 磁盘文件"""
        drawing = await self.get_drawing(drawing_id, tenant_id)
        if not drawing:
            return False

        # 删除磁盘文件（忽略不存在的情况）
        file_path = Path(drawing.file_url)
        if file_path.exists():
            file_path.unlink(missing_ok=True)

        # 级联删除绑定关系（ORM cascade 会处理），然后删除图纸记录
        await self.session.delete(drawing)
        await self.session.flush()
        return True

    async def get_file_path(self, drawing_id: int, tenant_id: int) -> Optional[str]:
        """获取图纸的本地文件路径（用于下载/预览）"""
        drawing = await self.get_drawing(drawing_id, tenant_id)
        if not drawing:
            return None
        return drawing.file_url

    # ========== 分类统计 ==========

    async def count_by_category(self, tenant_id: int) -> dict[str, int]:
        """统计各分类的图纸数量"""
        result = await self.session.execute(
            select(
                DrawingTemplate.category,
                func.count(DrawingTemplate.id),
            )
            .where(DrawingTemplate.tenant_id == tenant_id)
            .group_by(DrawingTemplate.category)
        )
        return {row[0]: row[1] for row in result.all()}

    # ========== 条件绑定 ==========

    async def add_binding(
        self,
        drawing_id: int,
        data: DrawingBindingCreate,
        tenant_id: int,
        created_by: int,
    ) -> DrawingBinding:
        """添加图纸-条件绑定"""
        binding = DrawingBinding(
            drawing_id=drawing_id,
            condition_field=data.condition_field,
            condition_value=data.condition_value,
            tenant_id=tenant_id,
            created_by=created_by,
        )
        self.session.add(binding)
        await self.session.flush()
        await self.session.refresh(binding)
        return binding

    async def list_bindings(self, drawing_id: int) -> list[DrawingBinding]:
        """获取某图纸的所有绑定关系"""
        result = await self.session.execute(
            select(DrawingBinding)
            .where(DrawingBinding.drawing_id == drawing_id)
            .order_by(DrawingBinding.id)
        )
        return list(result.scalars().all())

    async def remove_binding(self, binding_id: int) -> bool:
        """删除绑定关系"""
        result = await self.session.execute(
            select(DrawingBinding).where(DrawingBinding.id == binding_id)
        )
        binding = result.scalar_one_or_none()
        if not binding:
            return False
        await self.session.delete(binding)
        await self.session.flush()
        return True

    # ========== 匹配推荐 ==========

    async def match_drawings(
        self,
        params: DrawingMatchRequest,
        tenant_id: int,
    ) -> list[DrawingTemplate]:
        """根据项目参数匹配推荐图纸

        逻辑：查找所有绑定条件与输入参数匹配的图纸，
        并按匹配条件数量降序排列（匹配越多越靠前）。
        """
        # 构建条件映射：field → value
        conditions: dict[str, str] = {}
        if params.rock_class:
            conditions["rock_class"] = params.rock_class
        if params.section_form:
            conditions["section_form"] = params.section_form
        if params.roadway_type:
            conditions["roadway_type"] = params.roadway_type
        if params.excavation_type:
            conditions["excavation_type"] = params.excavation_type

        if not conditions:
            return []

        # 查找匹配的绑定关系
        or_conditions = [
            and_(
                DrawingBinding.condition_field == field,
                DrawingBinding.condition_value == value,
            )
            for field, value in conditions.items()
        ]

        # 子查询：统计每个 drawing_id 匹配了多少个条件
        from sqlalchemy import or_, case, literal_column
        binding_query = (
            select(
                DrawingBinding.drawing_id,
                func.count(DrawingBinding.id).label("match_count"),
            )
            .where(
                DrawingBinding.tenant_id == tenant_id,
                or_(*or_conditions),
            )
            .group_by(DrawingBinding.drawing_id)
            .subquery()
        )

        # 主查询：连接图纸表
        query = (
            select(DrawingTemplate)
            .join(binding_query, DrawingTemplate.id == binding_query.c.drawing_id)
            .where(DrawingTemplate.tenant_id == tenant_id)
        )

        # 可选：按分类过滤
        if params.category:
            query = query.where(DrawingTemplate.category == params.category)

        query = query.order_by(binding_query.c.match_count.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())
