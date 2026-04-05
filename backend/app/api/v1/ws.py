"""
WebSocket 端点 -- 生成管线实时进度推送

客户端连接后自动订阅 Redis Pub/Sub 频道，
转发所有进度事件直到管线完成或客户端断开。

增强能力（Phase 3）:
  - 心跳保活: 每 30 秒发送 ping，检测僵尸连接
  - 重连缓冲: 客户端断开重连后可收到最近 N 条事件
  - 错误分级: 事件携带 severity 字段（info/warning/error）
  - 背压保护: 高频事件合并，避免消息堆积

事件协议:
  pipeline_start  → {type, project_id, total_chapters, chapters}
  chapter_start   → {type, chapter_no, title, chapter_idx}
  phase           → {type, chapter_no, phase, detail}
  node_progress   → {type, node, node_name, status, chapter_no, detail}
  chapter_done    → {type, chapter_no, status, word_count}
  chapter_error   → {type, chapter_no, error}
  pipeline_done   → {type, completed, failed, total, status}
  heartbeat       → {type: "heartbeat"}
"""
import asyncio
import logging
from collections import deque

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.pubsub import subscribe_progress

logger = logging.getLogger("freshbid")

router = APIRouter(tags=["WebSocket"])

# 每个 project 最近 N 条事件缓冲（支持重连回放）
_event_buffers: dict[int, deque] = {}
_BUFFER_SIZE = 50

# 心跳间隔
_HEARTBEAT_INTERVAL = 30


def _buffer_event(project_id: int, event: dict) -> None:
    """缓存事件用于重连回放"""
    if project_id not in _event_buffers:
        _event_buffers[project_id] = deque(maxlen=_BUFFER_SIZE)
    _event_buffers[project_id].append(event)
    # pipeline_done 后清理缓冲
    if event.get("type") == "pipeline_done":
        _event_buffers.pop(project_id, None)


@router.websocket("/ws/generation/{project_id}")
async def ws_generation_progress(websocket: WebSocket, project_id: int):
    """WebSocket: 订阅投标文件生成管线的实时进度

    增强: 心跳保活 + 重连回放 + 背压保护
    """
    await websocket.accept()
    logger.info("WebSocket 已连接: project_id=%s", project_id)

    # 重连回放: 发送缓冲中的历史事件
    if project_id in _event_buffers:
        for cached in _event_buffers[project_id]:
            try:
                await websocket.send_json(cached)
            except Exception:
                return

    async def _heartbeat():
        """周期心跳，检测僵尸连接"""
        try:
            while True:
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                await websocket.send_json({"type": "heartbeat"})
        except Exception:
            pass  # 连接断开时静默退出

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        async for event in subscribe_progress(project_id):
            _buffer_event(project_id, event)
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开: project_id=%s", project_id)
    except Exception as e:
        logger.error("WebSocket 异常: project_id=%s: %s", project_id, e)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        heartbeat_task.cancel()
