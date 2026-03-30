"""
知识库 Schema — 工程案例 + 文档模板 + 章节片段

DAT-02: 工程案例（历史项目经验）
DAT-03: 文档模板（Word 模板管理）
DAT-04: 章节片段（可复用的规程内容块）
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ========== DAT-02 工程案例 ==========

class BidCaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="案例名称")
    customer_type: Optional[str] = Field(None, max_length=20, description="客户类型")
    buyer_name: Optional[str] = Field(None, max_length=200, description="采购方名称")
    bid_amount: Optional[str] = Field(None, max_length=50, description="中标金额")
    discount_rate: Optional[str] = Field(None, max_length=20, description="下浮率")
    summary: Optional[str] = Field(None, description="案例摘要/技术亮点")
    file_url: Optional[str] = Field(None, description="案例文件地址")


class BidCaseUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    customer_type: Optional[str] = None
    buyer_name: Optional[str] = None
    bid_amount: Optional[str] = None
    discount_rate: Optional[str] = None
    summary: Optional[str] = None
    file_url: Optional[str] = None


class BidCaseOut(BaseModel):
    id: int
    title: str
    customer_type: Optional[str] = None
    buyer_name: Optional[str] = None
    bid_amount: Optional[str] = None
    discount_rate: Optional[str] = None
    summary: Optional[str] = None
    file_url: Optional[str] = None
    tenant_id: int
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ========== DAT-03 文档模板 ==========

class DocTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="模板名称")
    description: Optional[str] = Field(None, description="模板描述")
    file_url: str = Field(description="模板文件地址")
    is_default: bool = Field(default=False, description="是否默认")


class DocTemplateOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    file_url: str
    is_default: bool
    tenant_id: int
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ========== DAT-04 章节片段 ==========

class ChapterSnippetCreate(BaseModel):
    chapter_no: str = Field(min_length=1, max_length=20, description="章节编号")
    chapter_name: str = Field(min_length=1, max_length=100, description="章节名称")
    content: str = Field(min_length=1, description="内容片段")
    sort_order: int = Field(default=0, description="排序权重")


class ChapterSnippetUpdate(BaseModel):
    chapter_no: Optional[str] = None
    chapter_name: Optional[str] = None
    content: Optional[str] = None
    sort_order: Optional[int] = None


class ChapterSnippetOut(BaseModel):
    id: int
    chapter_no: str
    chapter_name: str
    content: str
    sort_order: int
    tenant_id: int
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
