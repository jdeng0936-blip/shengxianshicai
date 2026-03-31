"""
计费模型 — 用户配额 + 用量记录

MVP 阶段：管理员手动分配配额，不接支付网关
后续 v2.0 对接支付宝/微信支付
"""
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, AuditMixin


class UserQuota(AuditMixin, Base):
    """用户配额表"""
    __tablename__ = "user_quota"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="用户ID")

    # 配额
    max_projects: Mapped[int] = mapped_column(Integer, default=5, comment="最大项目数")
    max_exports: Mapped[int] = mapped_column(Integer, default=10, comment="最大导出次数")
    max_ai_calls: Mapped[int] = mapped_column(Integer, default=100, comment="最大AI调用次数")

    # 已用量
    used_projects: Mapped[int] = mapped_column(Integer, default=0, comment="已用项目数")
    used_exports: Mapped[int] = mapped_column(Integer, default=0, comment="已用导出次数")
    used_ai_calls: Mapped[int] = mapped_column(Integer, default=0, comment="已用AI调用次数")

    # 套餐类型
    plan_type: Mapped[str] = mapped_column(
        String(20), default="free", comment="套餐: free/basic/pro/enterprise"
    )


class UsageLog(AuditMixin, Base):
    """用量记录表"""
    __tablename__ = "usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="用户ID")
    action: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="操作: create_project/export_doc/ai_generate/ai_rewrite/compliance_check"
    )
    resource_id: Mapped[int] = mapped_column(Integer, nullable=True, comment="关联资源ID（项目ID等）")
    detail: Mapped[str] = mapped_column(Text, nullable=True, comment="操作详情")
