"""
投标项目 + 招标要求 + 投标章节 模型

BidProject: 投标项目主表（替代原 Project）
TenderRequirement: 招标文件解析出的结构化要求
BidChapter: 投标文件章节内容
"""
import enum

from sqlalchemy import String, Integer, Float, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, AuditMixin


class BidProjectStatus(str, enum.Enum):
    """投标项目状态"""
    DRAFT = "draft"                 # 草稿
    PARSING = "parsing"             # 招标文件解析中
    PARSED = "parsed"               # 解析完成
    GENERATING = "generating"       # 投标文件生成中
    GENERATED = "generated"         # 生成完成
    REVIEWING = "reviewing"         # 合规审查中
    COMPLETED = "completed"         # 已完成
    SUBMITTED = "submitted"         # 已提交投标
    WON = "won"                     # 已中标
    LOST = "lost"                   # 未中标
    FAILED = "failed"               # 生成失败


class CustomerType(str, enum.Enum):
    """客户类型（决定模板选择）"""
    SCHOOL = "school"               # 学校食堂
    HOSPITAL = "hospital"           # 医院
    GOVERNMENT = "government"       # 政府机关
    ENTERPRISE = "enterprise"       # 企业食堂
    CANTEEN_COMPANY = "canteen"     # 团餐公司


class TenderType(str, enum.Enum):
    """招标方式"""
    OPEN = "open"                   # 公开招标
    INVITE = "invite"               # 邀请招标
    NEGOTIATE = "negotiate"         # 竞争性谈判
    INQUIRY = "inquiry"             # 询价
    SINGLE = "single"               # 单一来源


class BidProject(AuditMixin, Base):
    """投标项目"""
    __tablename__ = "bid_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="租户ID")
    enterprise_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("enterprise.id"), nullable=True, comment="投标企业ID"
    )

    # --- 招标方信息 ---
    project_name: Mapped[str] = mapped_column(String(300), nullable=False, comment="招标项目名称")
    tender_org: Mapped[str] = mapped_column(String(200), nullable=True, comment="招标方/采购方名称")
    tender_contact: Mapped[str] = mapped_column(String(200), nullable=True, comment="招标方联系方式")

    # --- 分类信息 ---
    customer_type: Mapped[str] = mapped_column(
        String(20), nullable=True, comment="客户类型: school/hospital/government/enterprise/canteen"
    )
    tender_type: Mapped[str] = mapped_column(
        String(20), nullable=True, comment="招标方式: open/invite/negotiate/inquiry/single"
    )

    # --- 时间节点 ---
    deadline: Mapped[str] = mapped_column(String(30), nullable=True, comment="投标截止时间")
    bid_opening_time: Mapped[str] = mapped_column(String(30), nullable=True, comment="开标时间")

    # --- 金额 ---
    budget_amount: Mapped[float] = mapped_column(Float, nullable=True, comment="预算金额（元）")
    bid_amount: Mapped[float] = mapped_column(Float, nullable=True, comment="我方报价金额（元）")

    # --- 配送信息 ---
    delivery_scope: Mapped[str] = mapped_column(Text, nullable=True, comment="配送范围描述")
    delivery_period: Mapped[str] = mapped_column(String(100), nullable=True, comment="配送周期/合同期限")

    # --- 状态 ---
    status: Mapped[str] = mapped_column(
        String(20), default=BidProjectStatus.DRAFT.value, comment="项目状态"
    )

    # --- 文件路径 ---
    tender_doc_path: Mapped[str] = mapped_column(Text, nullable=True, comment="上传的招标文件路径")
    bid_doc_path: Mapped[str] = mapped_column(Text, nullable=True, comment="生成的投标文件路径")

    # --- 备注 ---
    description: Mapped[str] = mapped_column(Text, nullable=True, comment="备注说明")

    # --- 关联 ---
    enterprise = relationship("Enterprise", lazy="selectin")
    requirements = relationship(
        "TenderRequirement", back_populates="project", lazy="selectin",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    chapters = relationship(
        "BidChapter", back_populates="project", lazy="selectin",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="BidChapter.sort_order",
    )
    quotation_sheets = relationship(
        "QuotationSheet", back_populates="project", lazy="selectin",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class RequirementCategory(str, enum.Enum):
    """招标要求分类"""
    QUALIFICATION = "qualification"         # 资格要求
    TECHNICAL = "technical"                  # 技术要求
    COMMERCIAL = "commercial"                # 商务要求
    SCORING = "scoring"                      # 评分标准
    DISQUALIFICATION = "disqualification"    # 废标项（最重要！）


class TenderRequirement(AuditMixin, Base):
    """招标文件解析出的结构化要求"""
    __tablename__ = "tender_requirement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bid_project.id", ondelete="CASCADE"), nullable=False
    )

    # --- 要求内容 ---
    category: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="分类: qualification/technical/commercial/scoring/disqualification"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="要求内容")
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否为强制要求")
    score_weight: Mapped[float] = mapped_column(Float, nullable=True, comment="评分权重（%）")
    max_score: Mapped[float] = mapped_column(Float, nullable=True, comment="最高分值")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序号")

    # --- 合规检查结果 ---
    compliance_status: Mapped[str] = mapped_column(
        String(20), nullable=True,
        comment="合规状态: passed/failed/warning/unchecked"
    )
    compliance_note: Mapped[str] = mapped_column(Text, nullable=True, comment="合规检查备注")

    # --- 关联 ---
    project = relationship("BidProject", back_populates="requirements")


class BidChapter(AuditMixin, Base):
    """投标文件章节"""
    __tablename__ = "bid_chapter"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bid_project.id", ondelete="CASCADE"), nullable=False
    )

    # --- 章节信息 ---
    chapter_no: Mapped[str] = mapped_column(String(30), nullable=False, comment="章节编号（第一章/4.3.1）")
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="章节标题")
    content: Mapped[str] = mapped_column(Text, nullable=True, comment="章节正文内容")

    # --- 元信息 ---
    source: Mapped[str] = mapped_column(
        String(20), default="template",
        comment="内容来源: template/ai/manual/credential"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="draft",
        comment="状态: draft/generated/reviewed/finalized"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序号（决定在文档中的顺序）")

    # --- AI 生成相关 ---
    ai_model_used: Mapped[str] = mapped_column(String(50), nullable=True, comment="使用的AI模型")
    ai_prompt_version: Mapped[str] = mapped_column(String(20), nullable=True, comment="使用的Prompt版本")
    has_warning: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否有合规警告")
    edit_ratio: Mapped[float] = mapped_column(
        Float, nullable=True, comment="用户编辑占比(0~1)，由反馈飞轮写入"
    )
    ai_ratio: Mapped[float] = mapped_column(
        Float, default=0.0, comment="AI原创占比(0~1)，高风险字段替换后降低"
    )
    source_tags: Mapped[str] = mapped_column(
        Text, default="", comment="内容来源标签，逗号分隔: ai_generated,company_db,template,credential"
    )

    # --- 关联 ---
    project = relationship("BidProject", back_populates="chapters")
