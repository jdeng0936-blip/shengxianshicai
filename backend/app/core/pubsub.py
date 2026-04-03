"""
Redis Pub/Sub -- 生成管线实时进度广播

架构:
  - 生成服务在各节点完成时 publish 事件到 Redis 频道
  - WebSocket 端点 subscribe 频道，转发给前端
  - 频道名: gen_progress:{project_id}
"""
import json
import logging
from typing import AsyncGenerator

from app.core.redis import get_redis

logger = logging.getLogger("freshbid")

CHANNEL_PREFIX = "gen_progress:"


def _channel(project_id: int) -> str:
    return f"{CHANNEL_PREFIX}{project_id}"


async def publish_progress(project_id: int, event: dict) -> None:
    """发布生成进度事件到 Redis 频道"""
    redis = get_redis()
    payload = json.dumps(event, ensure_ascii=False)
    await redis.publish(_channel(project_id), payload)


async def subscribe_progress(project_id: int) -> AsyncGenerator[dict, None]:
    """订阅生成进度事件流

    在收到 pipeline_done 事件或连接中断后自动退出。
    """
    redis = get_redis()
    pubsub = redis.pubsub()
    channel = _channel(project_id)
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                yield data
                if data.get("type") == "pipeline_done":
                    break
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
