"""
商机公告模型 — 招标公告线索池

定位：从外部采集的招标公告"线索"，区别于 BidProject（已决定投标的项目）。
流转：TenderNotice(new) → AI分析(analyzed/recommended) → 用户确认 → 转化为 BidProject(converted)

多租户隔离：tenant_id 强制过滤
"""
import enum

from sqlalchemy import String, Integer, Float, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, AuditMixin


class TenderNoticeStatus(str, enum.Enum):
    NEW = "new"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    RECOMMENDED = "recommended"
    DISMISSED = "dismissed"
    CONVERTED = "converted"
    EXPIRED = "expired"


class TenderNotice(AuditMixin, Base):
    """商机公告"""
    __tablename__ = "tender_notice"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="租户ID")
    enterprise_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("enterprise.id"), nullable=True, comment="匹配分析的目标企业"
    )

    # --- 来源信息 ---
    source: Mapped[str] = mapped_column(String(50), default="manual", comment="来源: manual/gov_procurement/mock")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="公告原始链接")
    source_id: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="外部唯一ID（去重用）")

    # --- 公告内容 ---
    title: Mapped[str] = mapped_column(String(500), nullable=False, comment="公告标题")
    buyer_name: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="采购方名称")
    buyer_region: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="所属地区")
    customer_type: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="客户类型")
    tender_type: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="招标方式")
    budget_amount: Mapped[float | None] = mapped_column(Float, nullable=True, comment="预算金额（元）")
    deadline: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="投标截止日期")
    publish_date: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="发布日期")
    delivery_scope: Mapped[str | None] = mapped_column(Text, nullable=True, comment="配送范围")
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="公告摘要/原文")

    # --- AI 分析结果 ---
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="匹配度 0-100")
    match_level: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="high/medium/low/risky")
    match_analysis: Mapped[str | None] = mapped_column(Text, nullable=True, comment="结构化分析JSON")
    capability_gaps: Mapped[str | None] = mapped_column(Text, nullable=True, comment="能力缺口JSON数组")
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True, comment="AI 投标建议")

    # --- 状态 ---
    status: Mapped[str] = mapped_column(String(20), default="new", comment="状态")
    converted_project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bid_project.id"), nullable=True, comment="转化后的投标项目ID"
    )

    # --- 关联 ---
    enterprise = relationship("Enterprise", lazy="selectin")

    __table_args__ = (
        Index("ix_tender_notice_tenant_status", "tenant_id", "status"),
        Index("ix_tender_notice_source_id", "source_id"),
    )
