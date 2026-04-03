"""
支付服务 — 订单管理 + 配额控制 + 回调处理

MVP 策略:
  - 支持手动转账 + 管理员开通（商户号未到位时的备用方案）
  - 预留支付宝/微信回调接口（商户号审批后接入）
  - 免费试用: 1篇带水印，不可重复领取
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import (
    PaymentOrder,
    Subscription,
    OrderStatus,
    SubscriptionType,
    PLAN_PRICES,
    PLAN_QUOTAS,
)


class PaymentService:
    """支付服务"""

    def __init__(self, session: AsyncSession, tenant_id: int):
        self.session = session
        self.tenant_id = tenant_id

    # ── 订单管理 ────────────────────────────────────────

    async def create_order(
        self, user_id: int, order_type: str, payment_method: str = "manual"
    ) -> dict:
        """创建支付订单

        Args:
            user_id: 下单用户 ID
            order_type: per_document | quarterly | yearly
            payment_method: alipay | wechat | manual

        Returns:
            {"order_no": str, "amount": float, "payment_method": str, "status": str}
        """
        # 校验套餐类型
        try:
            sub_type = SubscriptionType(order_type)
        except ValueError:
            raise ValueError(f"无效套餐类型: {order_type}")

        if sub_type == SubscriptionType.FREE_TRIAL:
            raise ValueError("免费试用无需创建订单")

        amount = PLAN_PRICES[sub_type]
        order_no = f"FBP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"

        order = PaymentOrder(
            order_no=order_no,
            user_id=user_id,
            tenant_id=self.tenant_id,
            created_by=user_id,
            order_type=order_type,
            amount=amount,
            quantity=1,
            payment_method=payment_method,
            status=OrderStatus.PENDING.value,
        )
        self.session.add(order)
        await self.session.flush()

        return {
            "order_id": order.id,
            "order_no": order_no,
            "amount": float(amount),
            "payment_method": payment_method,
            "status": OrderStatus.PENDING.value,
        }

    async def handle_callback(self, order_no: str, trade_no: str) -> bool:
        """处理支付回调（支付宝/微信/手动确认）

        Args:
            order_no: 本系统订单号
            trade_no: 第三方支付交易号（手动开通时填管理员备注）

        Returns:
            是否处理成功
        """
        result = await self.session.execute(
            select(PaymentOrder).where(
                PaymentOrder.order_no == order_no,
                PaymentOrder.tenant_id == self.tenant_id,
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            return False

        if order.status != OrderStatus.PENDING.value:
            return False

        # 更新订单状态
        order.status = OrderStatus.PAID.value
        order.payment_trade_no = trade_no
        order.paid_at = datetime.now(timezone.utc)

        # 开通/续费订阅
        sub_type = SubscriptionType(order.order_type)
        await self._activate_subscription(sub_type)

        return True

    async def get_order_list(self, user_id: int, page: int = 1, page_size: int = 20) -> dict:
        """获取订单列表"""
        from sqlalchemy import func

        base_filter = [
            PaymentOrder.tenant_id == self.tenant_id,
            PaymentOrder.user_id == user_id,
        ]

        total = (await self.session.execute(
            select(func.count()).where(*base_filter)
        )).scalar() or 0

        rows = (await self.session.execute(
            select(PaymentOrder)
            .where(*base_filter)
            .order_by(PaymentOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )).scalars().all()

        items = [
            {
                "id": o.id,
                "order_no": o.order_no,
                "order_type": o.order_type,
                "amount": float(o.amount),
                "status": o.status,
                "payment_method": o.payment_method,
                "paid_at": str(o.paid_at) if o.paid_at else None,
                "created_at": str(o.created_at) if o.created_at else None,
            }
            for o in rows
        ]
        return {"items": items, "total": total, "page": page}

    # ── 订阅/配额管理 ──────────────────────────────────

    async def get_or_create_subscription(self) -> Subscription:
        """获取当前租户的订阅记录（不存在则创建免费试用）"""
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.tenant_id == self.tenant_id,
            )
        )
        sub = result.scalar_one_or_none()
        if not sub:
            sub = Subscription(
                tenant_id=self.tenant_id,
                created_by=0,
                plan_type=SubscriptionType.FREE_TRIAL.value,
                total_quota=PLAN_QUOTAS[SubscriptionType.FREE_TRIAL],
                used_count=0,
            )
            self.session.add(sub)
            await self.session.flush()
        return sub

    async def check_quota(self) -> dict:
        """检查当前租户配额

        Returns:
            {"plan_type": str, "remaining_quota": int, "is_active": bool,
             "total_quota": int, "used_count": int, "end_date": str|None}
        """
        sub = await self.get_or_create_subscription()
        return {
            "plan_type": sub.plan_type,
            "remaining_quota": sub.remaining_quota,
            "is_active": sub.is_active,
            "total_quota": sub.total_quota,
            "used_count": sub.used_count,
            "end_date": str(sub.end_date) if sub.end_date else None,
        }

    async def consume_quota(self) -> bool:
        """消耗一次配额（在标书生成/导出时调用）

        Returns:
            是否扣减成功
        """
        sub = await self.get_or_create_subscription()
        if not sub.is_active:
            return False
        sub.used_count += 1
        return True

    async def is_free_trial_used(self) -> bool:
        """检查是否已使用免费试用"""
        sub = await self.get_or_create_subscription()
        if sub.plan_type != SubscriptionType.FREE_TRIAL.value:
            return False
        return sub.used_count > 0

    # ── 内部方法 ────────────────────────────────────────

    async def _activate_subscription(self, plan_type: SubscriptionType) -> None:
        """支付成功后开通/续费订阅"""
        sub = await self.get_or_create_subscription()
        now = datetime.now(timezone.utc)

        if plan_type == SubscriptionType.PER_DOCUMENT:
            # 按篇付费: 在现有基础上追加 1 篇配额
            sub.total_quota += PLAN_QUOTAS[plan_type]
            # 首次付费时切换套餐类型
            if sub.plan_type == SubscriptionType.FREE_TRIAL.value:
                sub.plan_type = plan_type.value

        elif plan_type == SubscriptionType.QUARTERLY:
            sub.plan_type = plan_type.value
            sub.total_quota += PLAN_QUOTAS[plan_type]
            # 有效期: 从当前时间起 90 天
            sub.start_date = now
            sub.end_date = now + timedelta(days=90)

        elif plan_type == SubscriptionType.YEARLY:
            sub.plan_type = plan_type.value
            sub.total_quota = PLAN_QUOTAS[plan_type]
            sub.start_date = now
            sub.end_date = now + timedelta(days=365)
