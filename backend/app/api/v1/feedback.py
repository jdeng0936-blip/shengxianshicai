"""
用户反馈飞轮 API — 采纳/修改/拒绝 闭环

架构红线：
  - 所有查询强制 tenant_id 隔离
  - AI 产出必须有反馈通道,数据沉淀至 feedback_log 表
  - 后续对接 LangFuse 打标 + SFT/RLHF 训练流水线
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload
from app.schemas.common import ApiResponse
from app.schemas.feedback import (
    DiffFeedbackRequest,
    FeedbackItem,
    FeedbackStats,
)
from app.models.feedback import FeedbackLog

router = APIRouter(prefix="/feedback", tags=["系统反馈飞轮"])


@router.post("")
async def submit_feedback(
    body: DiffFeedbackRequest,
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """
    提交一条反馈记录。

    前端用户对 AI 生成文档内容的修正（Diff 反馈），
    作为构建数据飞轮的关键正负样本积累（SFT/RLHF）。
    """
    tenant_id = int(payload.get("tenant_id", 0)) if payload else 0
    user_id = int(payload.get("sub", 0)) if payload else 0

    record = FeedbackLog(
        project_id=body.project_id,
        chapter_no=body.chapter_no,
        chapter_title=body.chapter_title,
        original_text=body.original_text,
        modified_text=body.modified_text,
        action=body.action,
        comment=body.comment,
        tenant_id=tenant_id,
        created_by=user_id,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)

    return ApiResponse(
        data={"id": record.id, "status": "recorded"}
    )


@router.get("")
async def list_feedback(
    project_id: int = Query(..., description="项目ID"),
    action: str | None = Query(None, description="按动作筛选: accept/edit/reject"),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """按项目查询反馈列表（强制 tenant_id 隔离）"""
    tenant_id = int(payload.get("tenant_id", 0)) if payload else 0

    stmt = (
        select(FeedbackLog)
        .where(FeedbackLog.tenant_id == tenant_id)
        .where(FeedbackLog.project_id == project_id)
        .order_by(FeedbackLog.created_at.desc())
    )
    if action:
        stmt = stmt.where(FeedbackLog.action == action)

    result = await session.execute(stmt)
    rows = result.scalars().all()

    items = [FeedbackItem.model_validate(r) for r in rows]
    return ApiResponse(data=items)


@router.get("/stats")
async def feedback_stats(
    project_id: int = Query(..., description="项目ID"),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """按项目聚合反馈统计（采纳率/修改率/拒绝率）"""
    tenant_id = int(payload.get("tenant_id", 0)) if payload else 0

    stmt = (
        select(FeedbackLog.action, func.count().label("cnt"))
        .where(FeedbackLog.tenant_id == tenant_id)
        .where(FeedbackLog.project_id == project_id)
        .group_by(FeedbackLog.action)
    )
    result = await session.execute(stmt)
    counts = {row.action: row.cnt for row in result}

    total = sum(counts.values())
    accept_count = counts.get("accept", 0)
    edit_count = counts.get("edit", 0)
    reject_count = counts.get("reject", 0)

    stats = FeedbackStats(
        total=total,
        accept_count=accept_count,
        edit_count=edit_count,
        reject_count=reject_count,
        accept_rate=round(accept_count / total, 4) if total else 0.0,
        edit_rate=round(edit_count / total, 4) if total else 0.0,
        reject_rate=round(reject_count / total, 4) if total else 0.0,
    )
    return ApiResponse(data=stats)
