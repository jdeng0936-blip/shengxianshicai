"""
用户反馈 API 路由 — 提交反馈 / 查询反馈 / 统计
"""
from typing import Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["用户反馈"])


class FeedbackSubmit(BaseModel):
    project_id: int
    chapter_no: str
    chapter_title: str
    original_text: str
    action: str = Field(description="accept / edit / reject")
    modified_text: Optional[str] = None
    comment: Optional[str] = None


@router.post("", response_model=ApiResponse)
async def submit_feedback(
    body: FeedbackSubmit,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """提交 AI 生成内容的反馈（采纳/编辑/拒绝）"""
    user_id = int(payload.get("sub", 0))
    svc = FeedbackService(session)
    log = await svc.submit_feedback(
        project_id=body.project_id,
        chapter_no=body.chapter_no,
        chapter_title=body.chapter_title,
        original_text=body.original_text,
        action=body.action,
        modified_text=body.modified_text,
        comment=body.comment,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    return ApiResponse(data={"id": log.id, "action": log.action, "diff_ratio": log.diff_ratio})


@router.get("", response_model=ApiResponse)
async def list_feedback(
    project_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """查询反馈列表"""
    svc = FeedbackService(session)
    items, total = await svc.list_feedback(tenant_id, project_id, page, page_size)
    return ApiResponse(data={
        "items": [
            {
                "id": f.id,
                "project_id": f.project_id,
                "chapter_no": f.chapter_no,
                "chapter_title": f.chapter_title,
                "action": f.action,
                "diff_ratio": f.diff_ratio,
                "comment": f.comment,
                "created_at": str(f.created_at) if f.created_at else None,
            }
            for f in items
        ],
        "total": total,
        "page": page,
    })


@router.get("/stats", response_model=ApiResponse)
async def feedback_stats(
    project_id: Optional[int] = None,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """反馈统计（采纳/编辑/拒绝比例 + 平均编辑差异度）"""
    svc = FeedbackService(session)
    stats = await svc.get_stats(tenant_id, project_id)
    return ApiResponse(data=stats)
