"""
用户反馈飞轮 — 数据模型

采纳/修改/拒绝 差分记录，作为 SFT/RLHF 数据飞轮的核心正负样本积累。
"""
from sqlalchemy import String, Integer, Float, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, AuditMixin


class FeedbackLog(AuditMixin, Base):
    """AI 生成内容的用户反馈记录"""
    __tablename__ = "feedback_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project.id"), nullable=False, comment="关联项目ID"
    )
    chapter_no: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="章节编号"
    )
    chapter_title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="章节标题"
    )
    original_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="AI 原始生成文本"
    )
    modified_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="用户修改后文本（reject 时可空）"
    )
    action: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="用户动作: accept / edit / reject"
    )
    comment: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="用户备注"
    )
    diff_ratio: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="编辑差异度 0~1（仅 edit 动作有值）"
    )

    __table_args__ = (
        Index("ix_feedback_project_action", "project_id", "action"),
        Index("ix_feedback_tenant", "tenant_id"),
    )
