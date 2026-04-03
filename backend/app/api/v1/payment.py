"""
支付 API 路由 — 订单创建 / 回调 / 订阅查询
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.services.payment_service import PaymentService

router = APIRouter(tags=["支付"])


# ── 请求体 Schema ───────────────────────────────────────

class CreateOrderRequest(BaseModel):
    order_type: str       # per_document | quarterly | yearly
    payment_method: str = "manual"  # alipay | wechat | manual


class CallbackRequest(BaseModel):
    order_no: str
    trade_no: str


# ── 订单接口 ────────────────────────────────────────────

@router.post("/payments/create-order", response_model=ApiResponse)
async def create_order(
    body: CreateOrderRequest,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """创建支付订单"""
    user_id = int(payload.get("sub", 0))
    svc = PaymentService(session, tenant_id)
    try:
        result = await svc.create_order(user_id, body.order_type, body.payment_method)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ApiResponse(data=result)


@router.post("/payments/callback/alipay", response_model=ApiResponse)
async def alipay_callback(
    body: CallbackRequest,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """支付宝支付回调"""
    svc = PaymentService(session, tenant_id)
    ok = await svc.handle_callback(body.order_no, body.trade_no)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单不存在或已处理")
    return ApiResponse(data={"message": "支付成功"})


@router.post("/payments/callback/wechat", response_model=ApiResponse)
async def wechat_callback(
    body: CallbackRequest,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """微信支付回调"""
    svc = PaymentService(session, tenant_id)
    ok = await svc.handle_callback(body.order_no, body.trade_no)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单不存在或已处理")
    return ApiResponse(data={"message": "支付成功"})


@router.get("/payments/orders", response_model=ApiResponse)
async def list_orders(
    page: int = 1,
    page_size: int = 20,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """获取订单列表"""
    user_id = int(payload.get("sub", 0))
    svc = PaymentService(session, tenant_id)
    result = await svc.get_order_list(user_id, page, page_size)
    return ApiResponse(data=result)


# ── 订阅接口 ────────────────────────────────────────────

@router.get("/subscriptions/current", response_model=ApiResponse)
async def get_current_subscription(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取当前订阅状态"""
    svc = PaymentService(session, tenant_id)
    result = await svc.check_quota()
    return ApiResponse(data=result)


@router.get("/subscriptions/check-quota", response_model=ApiResponse)
async def check_quota(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """检查是否有剩余配额（标书生成前调用）"""
    svc = PaymentService(session, tenant_id)
    quota = await svc.check_quota()
    if not quota["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="配额不足，请升级套餐",
        )
    return ApiResponse(data=quota)
