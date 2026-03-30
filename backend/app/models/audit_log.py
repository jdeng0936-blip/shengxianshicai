"""
操作审计日志模型
"""
from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """操作审计日志表

    记录系统中所有关键操作，用于安全审计和问题追踪。
    不混入 AuditMixin，因为日志表有自己的 tenant_id 和 created_at 语义。
    """
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="操作用户ID")
    username: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作用户名（冗余，防止用户删除后丢失）")
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="操作类型(create/update/delete/login/export)")
    resource: Mapped[str] = mapped_column(String(100), nullable=False, comment="操作资源(user/role/enterprise/bid_project/credential/...)")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="操作详情描述")
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True, comment="操作IP地址")
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="租户ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="操作时间",
    )
