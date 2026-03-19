"""
AI 对话 API 路由 — SSE 流式输出 + 非流式

架构红线：
  - 单向流式输出用 SSE
  - AIRouter 需要 DB session 以支持标准库语义检索
"""
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload
from app.schemas.common import ApiResponse
from app.schemas.ai import ChatRequest, ChatResponse
from app.services.ai_router import AIRouter
from app.services.industry_vocab import IndustryVocabService

router = APIRouter(prefix="/ai", tags=["AI 智能路由"])


@router.get("/industries", response_model=ApiResponse)
async def list_industries():
    """获取可用行业词库列表（前端下拉框数据源）"""
    return ApiResponse(data=IndustryVocabService.list_industries())


@router.post("/chat")
async def ai_chat(
    body: ChatRequest,
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """AI 对话 — 自然语言驱动计算引擎 + 标准库语义检索

    支持两种模式：
    - stream=true → SSE 流式输出（默认）
    - stream=false → 完整 JSON 响应
    """
    # 从 JWT payload 提取 tenant_id 强制传入路与系统隔离
    tenant_id = int(payload.get("tenant_id", 0)) if payload else 0
    # 每次请求创建新的 AIRouter 实例，注入 DB session
    ai = AIRouter(session=session, tenant_id=tenant_id, industry_type=body.industry_type)

    # 构建历史消息
    history = [{"role": m.role, "content": m.content} for m in body.history]

    if body.stream:
        # SSE 流式输出
        return StreamingResponse(
            ai.chat_stream(body.message, history),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # 非流式
        reply = await ai.chat(body.message, history)
        return ApiResponse(data=ChatResponse(reply=reply))
