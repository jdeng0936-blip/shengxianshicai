"""
AI 对话历史管理 — Schema

对话会话和消息的请求/响应模型。
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ChatSessionItem(BaseModel):
    """会话列表条目"""
    id: int
    title: Optional[str] = None
    project_id: Optional[int] = None
    industry_type: str = "fresh_food"
    is_archived: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message_count: int = 0

    model_config = {"from_attributes": True}


class ChatSessionCreate(BaseModel):
    """创建新会话"""
    project_id: Optional[int] = Field(None, description="关联项目ID")
    industry_type: str = Field("fresh_food", description="行业类型")
    title: Optional[str] = Field(None, max_length=200, description="会话标题")


class ChatMessageItem(BaseModel):
    """消息条目"""
    id: int
    session_id: int
    role: str
    content: str
    tool_calls: Optional[dict] = None
    tool_name: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ChatWithSessionRequest(BaseModel):
    """带会话管理的对话请求"""
    session_id: Optional[int] = Field(None, description="会话ID（不填则自动创建新会话）")
    message: str = Field(min_length=1, description="用户输入")
    project_id: Optional[int] = Field(None, description="关联项目ID（仅新建会话时生效）")
    stream: bool = Field(default=True, description="是否 SSE 流式输出")
    industry_type: str = Field("fresh_food", description="行业类型")
