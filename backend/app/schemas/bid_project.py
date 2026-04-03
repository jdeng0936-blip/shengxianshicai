"""
投标项目 Schema — Pydantic V2

覆盖：BidProject / TenderRequirement / BidChapter CRUD
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ========== TenderRequirement ==========

class TenderRequirementCreate(BaseModel):
    """创建招标要求"""
    category: str = Field(description="分类: qualification/technical/commercial/scoring/disqualification")
    content: str = Field(min_length=1, description="要求内容")
    is_mandatory: bool = Field(True, description="是否为强制要求")
    score_weight: Optional[float] = Field(None, description="评分权重（%）")
    max_score: Optional[float] = Field(None, description="最高分值")
    sort_order: int = Field(0, description="排序号")


class TenderRequirementUpdate(BaseModel):
    """更新招标要求"""
    category: Optional[str] = None
    content: Optional[str] = None
    is_mandatory: Optional[bool] = None
    score_weight: Optional[float] = None
    max_score: Optional[float] = None
    sort_order: Optional[int] = None
    compliance_status: Optional[str] = Field(None, description="合规状态: passed/failed/warning/unchecked")
    compliance_note: Optional[str] = None


class TenderRequirementOut(BaseModel):
    """招标要求输出"""
    id: int
    project_id: int
    category: str
    content: str
    is_mandatory: bool
    score_weight: Optional[float] = None
    max_score: Optional[float] = None
    sort_order: int = 0
    compliance_status: Optional[str] = None
    compliance_note: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ========== BidChapter ==========

class BidChapterCreate(BaseModel):
    """创建投标章节"""
    chapter_no: str = Field(min_length=1, max_length=30, description="章节编号")
    title: str = Field(min_length=1, max_length=200, description="章节标题")
    content: Optional[str] = Field(None, description="章节正文内容")
    source: str = Field("template", description="内容来源: template/ai/manual/credential")
    sort_order: int = Field(0, description="排序号")


class BidChapterUpdate(BaseModel):
    """更新投标章节"""
    chapter_no: Optional[str] = Field(None, max_length=30)
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = Field(None, description="状态: draft/generated/reviewed/finalized")
    sort_order: Optional[int] = None
    has_warning: Optional[bool] = None


class BidChapterOut(BaseModel):
    """投标章节输出"""
    id: int
    project_id: int
    chapter_no: str
    title: str
    content: Optional[str] = None
    source: str = "template"
    status: str = "draft"
    sort_order: int = 0
    ai_model_used: Optional[str] = None
    ai_prompt_version: Optional[str] = None
    has_warning: bool = False
    edit_ratio: Optional[float] = None
    ai_ratio: float = 0.0
    source_tags: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ========== BidProject ==========

class BidProjectCreate(BaseModel):
    """创建投标项目"""
    project_name: str = Field(min_length=1, max_length=300, description="招标项目名称")
    enterprise_id: Optional[int] = Field(None, description="投标企业ID")
    tender_org: Optional[str] = Field(None, max_length=200, description="招标方名称")
    tender_contact: Optional[str] = Field(None, max_length=200, description="招标方联系方式")
    customer_type: Optional[str] = Field(None, description="客户类型: school/hospital/government/enterprise/canteen")
    tender_type: Optional[str] = Field(None, description="招标方式: open/invite/negotiate/inquiry/single")
    deadline: Optional[str] = Field(None, max_length=30, description="投标截止时间")
    bid_opening_time: Optional[str] = Field(None, max_length=30, description="开标时间")
    budget_amount: Optional[float] = Field(None, description="预算金额（元）")
    delivery_scope: Optional[str] = Field(None, description="配送范围描述")
    delivery_period: Optional[str] = Field(None, max_length=100, description="配送周期/合同期限")
    description: Optional[str] = Field(None, description="备注说明")


class BidProjectUpdate(BaseModel):
    """更新投标项目"""
    project_name: Optional[str] = Field(None, max_length=300)
    enterprise_id: Optional[int] = None
    tender_org: Optional[str] = Field(None, max_length=200)
    tender_contact: Optional[str] = Field(None, max_length=200)
    customer_type: Optional[str] = None
    tender_type: Optional[str] = None
    deadline: Optional[str] = Field(None, max_length=30)
    bid_opening_time: Optional[str] = Field(None, max_length=30)
    budget_amount: Optional[float] = None
    bid_amount: Optional[float] = None
    delivery_scope: Optional[str] = None
    delivery_period: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = None
    description: Optional[str] = None


class BidProjectOut(BaseModel):
    """投标项目输出"""
    id: int
    tenant_id: int
    enterprise_id: Optional[int] = None
    project_name: str
    tender_org: Optional[str] = None
    tender_contact: Optional[str] = None
    customer_type: Optional[str] = None
    tender_type: Optional[str] = None
    deadline: Optional[str] = None
    bid_opening_time: Optional[str] = None
    budget_amount: Optional[float] = None
    bid_amount: Optional[float] = None
    delivery_scope: Optional[str] = None
    delivery_period: Optional[str] = None
    status: str = "draft"
    tender_doc_path: Optional[str] = None
    bid_doc_path: Optional[str] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # 嵌套关联
    requirements: List[TenderRequirementOut] = []
    chapters: List[BidChapterOut] = []

    model_config = ConfigDict(from_attributes=True)


class BidProjectListOut(BaseModel):
    """投标项目列表输出（不含嵌套）"""
    id: int
    tenant_id: int
    enterprise_id: Optional[int] = None
    project_name: str
    tender_org: Optional[str] = None
    customer_type: Optional[str] = None
    tender_type: Optional[str] = None
    deadline: Optional[str] = None
    budget_amount: Optional[float] = None
    bid_amount: Optional[float] = None
    status: str = "draft"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
