"""
图片资源库 API 路由 — ImageAsset CRUD + 文件上传
"""
import os
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.schemas.image_asset import ImageAssetCreate, ImageAssetUpdate, ImageAssetOut
from app.services.image_asset_service import ImageAssetService

router = APIRouter(prefix="/images", tags=["图片资源库"])

IMAGE_UPLOAD_ROOT = Path("storage/images")
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


@router.get("/enterprise/{enterprise_id}", response_model=ApiResponse[list[ImageAssetOut]])
async def list_images(
    enterprise_id: int,
    category: Optional[str] = Query(None, description="按分类筛选"),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取企业的图片资源列表"""
    svc = ImageAssetService(session)
    items = await svc.list_by_enterprise(enterprise_id, tenant_id, category)
    return ApiResponse(data=[ImageAssetOut.model_validate(i) for i in items])


@router.get("/enterprise/{enterprise_id}/defaults", response_model=ApiResponse[list[ImageAssetOut]])
async def get_default_images(
    enterprise_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取每个分类的默认图片（AI文档生成时使用）"""
    svc = ImageAssetService(session)
    items = await svc.get_defaults_by_category(enterprise_id, tenant_id)
    return ApiResponse(data=[ImageAssetOut.model_validate(i) for i in items])


@router.post("/upload", response_model=ApiResponse[ImageAssetOut])
async def upload_image(
    file: UploadFile = File(..., description="图片文件"),
    enterprise_id: int = Form(...),
    category: str = Form("other"),
    title: str = Form(""),
    description: Optional[str] = Form(None),
    suggested_chapter: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """上传图片文件并创建记录"""
    user_id = int(payload.get("sub", 0))
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_IMAGE_EXTS:
        raise HTTPException(status_code=400, detail=f"不支持的图片格式: {ext}")

    # 保存文件
    save_dir = IMAGE_UPLOAD_ROOT / str(tenant_id) / str(enterprise_id)
    save_dir.mkdir(parents=True, exist_ok=True)
    save_name = f"{uuid.uuid4().hex}{ext}"
    save_path = save_dir / save_name

    content = await file.read()
    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    # 获取图片尺寸
    width, height = None, None
    try:
        from PIL import Image
        img = Image.open(save_path)
        width, height = img.size
        img.close()
    except Exception:
        pass

    # 创建数据库记录
    data = ImageAssetCreate(
        enterprise_id=enterprise_id,
        category=category,
        title=title or os.path.splitext(filename)[0],
        description=description,
        file_path=str(save_path),
        file_name=filename,
        file_size=len(content),
        mime_type=file.content_type,
        width=width,
        height=height,
        tags=tags,
        suggested_chapter=suggested_chapter,
    )
    svc = ImageAssetService(session)
    image = await svc.create_image(data, tenant_id, user_id)
    return ApiResponse(data=ImageAssetOut.model_validate(image))


@router.get("/file/{image_id}")
async def serve_image(
    image_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取图片文件"""
    svc = ImageAssetService(session)
    image = await svc.get_image(image_id, tenant_id)
    if not image or not os.path.exists(image.file_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(
        path=image.file_path,
        media_type=image.mime_type or "image/jpeg",
        filename=image.file_name,
    )


@router.get("/{image_id}", response_model=ApiResponse[ImageAssetOut])
async def get_image(
    image_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取图片资源详情"""
    svc = ImageAssetService(session)
    image = await svc.get_image(image_id, tenant_id)
    if not image:
        raise HTTPException(status_code=404, detail="图片资源不存在")
    return ApiResponse(data=ImageAssetOut.model_validate(image))


@router.post("", response_model=ApiResponse[ImageAssetOut])
async def create_image(
    body: ImageAssetCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """创建图片资源记录"""
    user_id = int(payload.get("sub", 0))
    svc = ImageAssetService(session)
    image = await svc.create_image(body, tenant_id, user_id)
    return ApiResponse(data=ImageAssetOut.model_validate(image))


@router.put("/{image_id}", response_model=ApiResponse[ImageAssetOut])
async def update_image(
    image_id: int,
    body: ImageAssetUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """更新图片资源"""
    svc = ImageAssetService(session)
    image = await svc.update_image(image_id, tenant_id, body)
    if not image:
        raise HTTPException(status_code=404, detail="图片资源不存在")
    return ApiResponse(data=ImageAssetOut.model_validate(image))


@router.delete("/{image_id}", response_model=ApiResponse)
async def delete_image(
    image_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除图片资源"""
    svc = ImageAssetService(session)
    ok = await svc.delete_image(image_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="图片资源不存在")
    return ApiResponse(data={"deleted": True})
