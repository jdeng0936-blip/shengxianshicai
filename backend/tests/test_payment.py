"""
支付服务单元测试 — Mock DB Session

测试策略:
  - 订单创建/回调: Mock session，验证业务逻辑
  - 配额管理: 验证免费试用、按篇付费、季度包、年度包配额逻辑
  - 不调用真实数据库或第三方支付
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone


def _load_payment():
    """延迟导入，避免 collect 阶段触发 Settings 校验"""
    from app.services.payment_service import PaymentService
    from app.models.payment import (
        Subscription, PaymentOrder, OrderStatus, SubscriptionType,
        PLAN_PRICES, PLAN_QUOTAS,
    )
    return PaymentService, Subscription, PaymentOrder, OrderStatus, SubscriptionType, PLAN_PRICES, PLAN_QUOTAS


def _mock_session():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _mock_subscription(plan_type="free_trial", total_quota=1, used_count=0, end_date=None):
    PaymentService, Subscription, *_ = _load_payment()
    sub = MagicMock(spec=Subscription)
    sub.plan_type = plan_type
    sub.total_quota = total_quota
    sub.used_count = used_count
    sub.end_date = end_date

    # 模拟 property
    if plan_type == "yearly":
        type(sub).remaining_quota = property(lambda s: 999999)
    else:
        type(sub).remaining_quota = property(lambda s: max(0, s.total_quota - s.used_count))

    def is_active_fn(s):
        if s.end_date and datetime.now(timezone.utc) > s.end_date:
            return False
        return s.remaining_quota > 0
    type(sub).is_active = property(is_active_fn)

    return sub


class TestCreateOrder:
    """订单创建测试"""

    @pytest.mark.asyncio
    async def test_create_per_document_order(self):
        """按篇付费订单创建成功"""
        PaymentService, *_ = _load_payment()
        svc = PaymentService(_mock_session(), tenant_id=1)
        result = await svc.create_order(user_id=1, order_type="per_document")
        assert result["amount"] == 199
        assert result["status"] == "pending"
        assert result["order_no"].startswith("FBP-")

    @pytest.mark.asyncio
    async def test_create_quarterly_order(self):
        """季度包订单创建成功"""
        PaymentService, *_ = _load_payment()
        svc = PaymentService(_mock_session(), tenant_id=1)
        result = await svc.create_order(user_id=1, order_type="quarterly")
        assert result["amount"] == 999

    @pytest.mark.asyncio
    async def test_create_yearly_order(self):
        """年度包订单创建成功"""
        PaymentService, *_ = _load_payment()
        svc = PaymentService(_mock_session(), tenant_id=1)
        result = await svc.create_order(user_id=1, order_type="yearly")
        assert result["amount"] == 2988

    @pytest.mark.asyncio
    async def test_free_trial_cannot_create_order(self):
        """免费试用不能创建订单"""
        PaymentService, *_ = _load_payment()
        svc = PaymentService(_mock_session(), tenant_id=1)
        with pytest.raises(ValueError, match="免费试用无需创建订单"):
            await svc.create_order(user_id=1, order_type="free_trial")

    @pytest.mark.asyncio
    async def test_invalid_order_type(self):
        """无效套餐类型"""
        PaymentService, *_ = _load_payment()
        svc = PaymentService(_mock_session(), tenant_id=1)
        with pytest.raises(ValueError, match="无效套餐类型"):
            await svc.create_order(user_id=1, order_type="invalid")


class TestQuotaManagement:
    """配额管理测试"""

    @pytest.mark.asyncio
    async def test_free_trial_has_one_quota(self):
        """免费试用有 1 次配额"""
        PaymentService, *_ = _load_payment()
        sub = _mock_subscription("free_trial", total_quota=1, used_count=0)
        svc = PaymentService(_mock_session(), tenant_id=1)

        with patch.object(svc, "get_or_create_subscription", return_value=sub):
            result = await svc.check_quota()
            assert result["plan_type"] == "free_trial"
            assert result["remaining_quota"] == 1
            assert result["is_active"] is True

    @pytest.mark.asyncio
    async def test_free_trial_exhausted(self):
        """免费试用用完 → 不可用"""
        PaymentService, *_ = _load_payment()
        sub = _mock_subscription("free_trial", total_quota=1, used_count=1)
        svc = PaymentService(_mock_session(), tenant_id=1)

        with patch.object(svc, "get_or_create_subscription", return_value=sub):
            result = await svc.check_quota()
            assert result["remaining_quota"] == 0
            assert result["is_active"] is False

    @pytest.mark.asyncio
    async def test_consume_quota_success(self):
        """配额充足时扣减成功"""
        PaymentService, *_ = _load_payment()
        sub = _mock_subscription("quarterly", total_quota=10, used_count=3)
        svc = PaymentService(_mock_session(), tenant_id=1)

        with patch.object(svc, "get_or_create_subscription", return_value=sub):
            ok = await svc.consume_quota()
            assert ok is True
            assert sub.used_count == 4

    @pytest.mark.asyncio
    async def test_consume_quota_fail_when_exhausted(self):
        """配额耗尽时扣减失败"""
        PaymentService, *_ = _load_payment()
        sub = _mock_subscription("per_document", total_quota=1, used_count=1)
        svc = PaymentService(_mock_session(), tenant_id=1)

        with patch.object(svc, "get_or_create_subscription", return_value=sub):
            ok = await svc.consume_quota()
            assert ok is False

    @pytest.mark.asyncio
    async def test_yearly_unlimited_quota(self):
        """年度包配额无限"""
        PaymentService, *_ = _load_payment()
        sub = _mock_subscription("yearly", total_quota=999999, used_count=500)
        svc = PaymentService(_mock_session(), tenant_id=1)

        with patch.object(svc, "get_or_create_subscription", return_value=sub):
            result = await svc.check_quota()
            assert result["remaining_quota"] == 999999
            assert result["is_active"] is True

    @pytest.mark.asyncio
    async def test_expired_subscription_inactive(self):
        """过期订阅不可用"""
        PaymentService, *_ = _load_payment()
        past = datetime.now(timezone.utc) - timedelta(days=1)
        sub = _mock_subscription("quarterly", total_quota=10, used_count=3, end_date=past)
        svc = PaymentService(_mock_session(), tenant_id=1)

        with patch.object(svc, "get_or_create_subscription", return_value=sub):
            result = await svc.check_quota()
            assert result["is_active"] is False

    @pytest.mark.asyncio
    async def test_is_free_trial_used(self):
        """免费试用已使用检查"""
        PaymentService, *_ = _load_payment()
        sub = _mock_subscription("free_trial", total_quota=1, used_count=1)
        svc = PaymentService(_mock_session(), tenant_id=1)

        with patch.object(svc, "get_or_create_subscription", return_value=sub):
            assert await svc.is_free_trial_used() is True

    @pytest.mark.asyncio
    async def test_is_free_trial_not_used(self):
        """免费试用未使用"""
        PaymentService, *_ = _load_payment()
        sub = _mock_subscription("free_trial", total_quota=1, used_count=0)
        svc = PaymentService(_mock_session(), tenant_id=1)

        with patch.object(svc, "get_or_create_subscription", return_value=sub):
            assert await svc.is_free_trial_used() is False


class TestPaymentCallback:
    """支付回调测试"""

    @pytest.mark.asyncio
    async def test_callback_order_not_found(self):
        """订单不存在 → 返回 False"""
        PaymentService, *_ = _load_payment()
        svc = PaymentService(_mock_session(), tenant_id=1)
        # session.execute 默认返回 scalar_one_or_none = None
        result = await svc.handle_callback("INVALID-ORDER", "TRADE-123")
        assert result is False

    @pytest.mark.asyncio
    async def test_callback_already_paid(self):
        """已支付订单重复回调 → 返回 False"""
        PaymentService, _, PaymentOrder, OrderStatus, *_ = _load_payment()
        order = MagicMock(spec=PaymentOrder)
        order.status = OrderStatus.PAID.value
        order.order_no = "FBP-TEST"
        order.order_type = "per_document"

        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = order
        session.execute = AsyncMock(return_value=mock_result)

        svc = PaymentService(session, tenant_id=1)
        result = await svc.handle_callback("FBP-TEST", "TRADE-123")
        assert result is False
