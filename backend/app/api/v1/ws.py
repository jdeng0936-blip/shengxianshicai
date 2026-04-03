"""
WebSocket 端点 -- 生成管线实时进度推送

客户端连接后自动订阅 Redis Pub/Sub 频道，
转发所有进度事件直到管线完成或客户端断开。

事件协议:
  pipeline_start  → {type, project_id, total_chapters, chapters: [{chapter_no, title}]}
  chapter_start   → {type, chapter_no, title, chapter_idx}
  phase           → {type, chapter_no, phase, detail}
  chapter_done    → {type, chapter_no, status, word_count}
  chapter_error   → {type, chapter_no, error}
  pipeline_done   → {type, completed, failed, total, status}
"""
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.pubsub import subscribe_progress

logger = logging.getLogger("freshbid")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/generation/{project_id}")
async def ws_generation_progress(websocket: WebSocket, project_id: int):
    """WebSocket: 订阅投标文件生成管线的实时进度"""
    await websocket.accept()
    logger.info("WebSocket 已连接: project_id=%s", project_id)

    try:
        async for event in subscribe_progress(project_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开: project_id=%s", project_id)
    except Exception as e:
        logger.error("WebSocket 异常: project_id=%s: %s", project_id, e)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
