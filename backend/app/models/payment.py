"""
支付模型 — 订单表 + 订阅/配额表

支付流程: 创建订单 → 第三方支付 → 回调更新 → 开通/续费订阅
"""
import enum
from typing import Optional

from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, AuditMixin


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    EXPIRED = "expired"


class SubscriptionType(str, enum.Enum):
    FREE_TRIAL = "free_trial"       # 免费试用（1篇带水印）
    PER_DOCUMENT = "per_document"   # 按篇付费 ¥199
    QUARTERLY = "quarterly"         # 季度包 ¥999/10篇
    YEARLY = "yearly"               # 年度包 ¥2988/不限


# 套餐价格表（单位：元）
PLAN_PRICES = {
    SubscriptionType.PER_DOCUMENT: 199,
    SubscriptionType.QUARTERLY: 999,
    SubscriptionType.YEARLY: 2988,
}

# 套餐配额
PLAN_QUOTAS = {
    SubscriptionType.FREE_TRIAL: 1,
    SubscriptionType.PER_DOCUMENT: 1,
    SubscriptionType.QUARTERLY: 10,
    SubscriptionType.YEARLY: 999999,
}


class PaymentOrder(AuditMixin, Base):
    """支付订单表"""
    __tablename__ = "payment_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="订单号"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sys_user.id"), nullable=False, comment="下单用户ID"
    )

    # 订单内容
    order_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="per_document|quarterly|yearly"
    )
    amount: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, comment="订单金额（元）"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, comment="数量（按篇付费时为1）"
    )

    # 支付信息
    payment_method: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="alipay|wechat|manual"
    )
    payment_trade_no: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="第三方支付交易号"
    )
    status: Mapped[str] = mapped_column(
        String(20), default=OrderStatus.PENDING.value, comment="订单状态"
    )
    paid_at: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="支付完成时间"
    )

    # 备注
    remark: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="备注"
    )

    __table_args__ = (
        Index("ix_payment_order_user", "user_id"),
        Index("ix_payment_order_tenant", "tenant_id"),
        Index("ix_payment_order_status", "status"),
    )


class Subscription(AuditMixin, Base):
    """订阅/配额表 — 每个租户一条记录"""
    __tablename__ = "subscription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 套餐类型
    plan_type: Mapped[str] = mapped_column(
        String(20), default=SubscriptionType.FREE_TRIAL.value,
        comment="free_trial|per_document|quarterly|yearly"
    )

    # 用量追踪
    total_quota: Mapped[int] = mapped_column(
        Integer, default=1, comment="总配额（免费试用=1）"
    )
    used_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="已使用次数"
    )

    # 有效期
    start_date: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="订阅开始时间"
    )
    end_date: Mapped[Optional[DateTime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="订阅到期时间"
    )

    __table_args__ = (
        Index("ix_subscription_tenant", "tenant_id", unique=True),
    )

    @property
    def remaining_quota(self) -> int:
        if self.plan_type == SubscriptionType.YEARLY.value:
            return 999999
        return max(0, self.total_quota - self.used_count)

    @property
    def is_active(self) -> bool:
        from datetime import datetime, timezone as tz
        if self.end_date and datetime.now(tz.utc) > self.end_date:
            return False
        return self.remaining_quota > 0
