"""
AI 智能路由 Schema — Pydantic V2

核心：用户自然语言 → LLM Tool Calling → 引擎调度 → 结构化结果
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """单条对话消息"""
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ChatRequest(BaseModel):
    """AI 对话请求"""
    message: str = Field(min_length=1, description="用户输入")
    project_id: Optional[int] = Field(None, description="关联项目ID（可选）")
    history: list[ChatMessage] = Field(default_factory=list, description="历史消息")
    stream: bool = Field(default=True, description="是否 SSE 流式输出")
    industry_type: str = Field(default="fresh_food", description="行业类型（决定词库注入）")


class ToolCallResult(BaseModel):
    """工具调用结果"""
    tool_name: str
    tool_args: dict
    result: dict


class ChatResponse(BaseModel):
    """AI 对话响应（非流式）"""
    reply: str = Field(description="AI 回复")
    tool_calls: list[ToolCallResult] = Field(default_factory=list,
                                              description="本轮调用的工具")
