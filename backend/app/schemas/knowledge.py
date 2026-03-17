"""
知识库 Schema — 工程案例 + 文档模板 + 章节片段

DAT-02: 工程案例（历史项目经验）
DAT-03: 文档模板（Word 模板管理）
DAT-04: 章节片段（可复用的规程内容块）
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


# ========== DAT-02 工程案例 ==========

class EngCaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="案例名称")
    mine_name: Optional[str] = Field(None, max_length=100, description="矿井名称")
    excavation_type: Optional[str] = Field(None, description="掘进类型")
    rock_class: Optional[str] = Field(None, description="围岩级别")
    summary: Optional[str] = Field(None, description="案例摘要")
    file_url: Optional[str] = Field(None, description="案例文件地址")


class EngCaseUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    mine_name: Optional[str] = None
    excavation_type: Optional[str] = None
    rock_class: Optional[str] = None
    summary: Optional[str] = None
    file_url: Optional[str] = None


class EngCaseOut(BaseModel):
    id: int
    title: str
    mine_name: Optional[str]
    excavation_type: Optional[str]
    rock_class: Optional[str]
    summary: Optional[str]
    file_url: Optional[str]
    tenant_id: int
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True
