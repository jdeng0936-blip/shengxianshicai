"""
图纸管理 API 路由

所有接口强制 JWT 认证 + tenant_id 隔离。
文件上传使用 multipart/form-data。
"""
import os
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.drawing import (
    DrawingCreate,
    DrawingUpdate,
    DrawingOut,
    DrawingBindingCreate,
    DrawingBindingOut,
    DrawingMatchRequest,
)
from app.services.drawing_service import DrawingService

router = APIRouter(prefix="/drawings", tags=["图纸管理"])


# ========== 图纸 CRUD ==========

@router.get("", response_model=ApiResponse[PaginatedData[DrawingOut]])
async def list_drawings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None, description="分类筛选"),
    name: Optional[str] = Query(None, description="名称模糊搜索"),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取图纸列表（分页 + 分类筛选）"""
    svc = DrawingService(session)
    items, total = await svc.list_drawings(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        category=category,
        name=name,
    )
    return ApiResponse(
        data=PaginatedData(
            items=[DrawingOut.model_validate(d) for d in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/categories", response_model=ApiResponse)
async def get_category_counts(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取各分类的图纸数量统计"""
    svc = DrawingService(session)
    counts = await svc.count_by_category(tenant_id)
    return ApiResponse(data=counts)


@router.post("/upload", response_model=ApiResponse[DrawingOut], status_code=201)
async def upload_drawing(
    file: UploadFile = File(..., description="图纸文件"),
    name: str = Form(..., description="图纸名称"),
    category: str = Form(..., description="分类(section/support/layout/schedule/safety/measure)"),
    description: Optional[str] = Form(None, description="图纸描述"),
    payload: dict = Depends(get_current_user_payload),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """上传图纸文件（multipart/form-data）"""
    data = DrawingCreate(name=name, category=category, description=description)
    svc = DrawingService(session)
    try:
        drawing = await svc.create_drawing(
            data=data,
            file=file,
            tenant_id=tenant_id,
            created_by=int(payload["sub"]),
        )
        await session.commit()
        return ApiResponse(data=DrawingOut.model_validate(drawing))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{drawing_id}", response_model=ApiResponse[DrawingOut])
async def get_drawing(
    drawing_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取图纸详情"""
    svc = DrawingService(session)
    drawing = await svc.get_drawing(drawing_id, tenant_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="图纸不存在")
    return ApiResponse(data=DrawingOut.model_validate(drawing))


@router.put("/{drawing_id}", response_model=ApiResponse[DrawingOut])
async def update_drawing(
    drawing_id: int,
    body: DrawingUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """更新图纸元信息"""
    svc = DrawingService(session)
    drawing = await svc.update_drawing(drawing_id, tenant_id, body)
    if not drawing:
        raise HTTPException(status_code=404, detail="图纸不存在")
    await session.commit()
    return ApiResponse(data=DrawingOut.model_validate(drawing))


@router.delete("/{drawing_id}", response_model=ApiResponse)
async def delete_drawing(
    drawing_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除图纸（含磁盘文件）"""
    svc = DrawingService(session)
    success = await svc.delete_drawing(drawing_id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="图纸不存在")
    await session.commit()
    return ApiResponse(message="删除成功")


@router.get("/{drawing_id}/file")
async def download_drawing_file(
    drawing_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """下载/预览图纸文件"""
    svc = DrawingService(session)
    file_path = await svc.get_file_path(drawing_id, tenant_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="图纸不存在")

    abs_path = Path(file_path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在或已被删除")

    return FileResponse(
        path=str(abs_path),
        filename=abs_path.name,
        media_type="application/octet-stream",
    )


# ========== 条件绑定 ==========

@router.get("/{drawing_id}/bindings", response_model=ApiResponse[list[DrawingBindingOut]])
async def list_bindings(
    drawing_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取图纸的条件绑定列表"""
    svc = DrawingService(session)
    # 验证图纸存在
    drawing = await svc.get_drawing(drawing_id, tenant_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="图纸不存在")
    bindings = await svc.list_bindings(drawing_id)
    return ApiResponse(data=[DrawingBindingOut.model_validate(b) for b in bindings])


@router.post("/{drawing_id}/bindings", response_model=ApiResponse[DrawingBindingOut], status_code=201)
async def add_binding(
    drawing_id: int,
    body: DrawingBindingCreate,
    payload: dict = Depends(get_current_user_payload),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """添加条件绑定"""
    svc = DrawingService(session)
    drawing = await svc.get_drawing(drawing_id, tenant_id)
    if not drawing:
        raise HTTPException(status_code=404, detail="图纸不存在")
    binding = await svc.add_binding(
        drawing_id=drawing_id,
        data=body,
        tenant_id=tenant_id,
        created_by=int(payload["sub"]),
    )
    await session.commit()
    return ApiResponse(data=DrawingBindingOut.model_validate(binding))


@router.delete("/bindings/{binding_id}", response_model=ApiResponse)
async def remove_binding(
    binding_id: int,
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """删除条件绑定"""
    svc = DrawingService(session)
    success = await svc.remove_binding(binding_id)
    if not success:
        raise HTTPException(status_code=404, detail="绑定关系不存在")
    await session.commit()
    return ApiResponse(message="删除成功")


# ========== 匹配推荐 ==========

@router.post("/match", response_model=ApiResponse[list[DrawingOut]])
async def match_drawings(
    body: DrawingMatchRequest,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """根据项目参数匹配推荐图纸"""
    svc = DrawingService(session)
    drawings = await svc.match_drawings(body, tenant_id)
    return ApiResponse(data=[DrawingOut.model_validate(d) for d in drawings])
