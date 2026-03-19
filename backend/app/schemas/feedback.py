"""
用户反馈飞轮 — Pydantic V2 Schema

入参校验 + 响应序列化。
"""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


# ---------- 请求 ----------
class DiffFeedbackRequest(BaseModel):
    """提交一条反馈"""
    project_id: int = Field(..., description="关联项目ID")
    chapter_no: str = Field(..., max_length=20, description="章节编号")
    chapter_title: str = Field(..., max_length=200, description="章节标题")
    original_text: str = Field(..., min_length=1, description="AI 原始生成文本")
    modified_text: str = Field(..., min_length=1, description="用户修正后文本")
    action: Literal["accept", "edit", "reject"] = Field(..., description="用户动作")
    comment: Optional[str] = Field(None, description="备注")


# ---------- 响应 ----------
class FeedbackItem(BaseModel):
    """单条反馈记录"""
    id: int
    project_id: int
    chapter_no: str
    chapter_title: str
    original_text: str
    modified_text: str
    action: str
    comment: Optional[str] = None
    created_at: datetime
    created_by: Optional[int] = None

    model_config = {"from_attributes": True}


class FeedbackStats(BaseModel):
    """反馈统计"""
    total: int = 0
    accept_count: int = 0
    edit_count: int = 0
    reject_count: int = 0
    accept_rate: float = Field(0.0, description="采纳率 0~1")
    edit_rate: float = Field(0.0, description="修改率 0~1")
    reject_rate: float = Field(0.0, description="拒绝率 0~1")
