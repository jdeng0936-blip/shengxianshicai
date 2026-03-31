"""
计费 API 路由 — 配额查询 / 用量统计 / 配额调整
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.services.billing_service import BillingService

router = APIRouter(prefix="/billing", tags=["计费中心"])


@router.get("/quota", response_model=ApiResponse)
async def get_quota(
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """获取当前用户配额和用量"""
    user_id = int(payload.get("sub", 0))
    svc = BillingService(session)
    stats = await svc.get_usage_stats(user_id, tenant_id)
    return ApiResponse(data=stats)


@router.get("/check/{action}", response_model=ApiResponse)
async def check_quota(
    action: str,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """检查指定操作是否有足够配额"""
    user_id = int(payload.get("sub", 0))
    svc = BillingService(session)
    result = await svc.check_quota(user_id, tenant_id, action)
    return ApiResponse(data=result)


@router.get("/usage-logs", response_model=ApiResponse)
async def list_usage_logs(
    page: int = 1,
    page_size: int = 20,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """获取用量日志"""
    from sqlalchemy import select, func
    from app.models.billing import UsageLog

    user_id = int(payload.get("sub", 0))

    # 总数
    count_q = select(func.count()).where(
        UsageLog.user_id == user_id, UsageLog.tenant_id == tenant_id
    )
    total = (await session.execute(count_q)).scalar() or 0

    # 分页查询
    q = (
        select(UsageLog)
        .where(UsageLog.user_id == user_id, UsageLog.tenant_id == tenant_id)
        .order_by(UsageLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(q)).scalars().all()

    items = [
        {
            "id": r.id,
            "action": r.action,
            "resource_id": r.resource_id,
            "detail": r.detail,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in rows
    ]
    return ApiResponse(data={"items": items, "total": total, "page": page})
