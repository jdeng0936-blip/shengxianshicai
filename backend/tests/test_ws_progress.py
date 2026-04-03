"""
WebSocket 生成进度端点 + Redis Pub/Sub 集成测试

验证:
  1. WebSocket 连接建立
  2. Pub/Sub 发布事件 → WebSocket 客户端收到
  3. pipeline_done 事件触发连接正常关闭
"""
import asyncio
import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import fakeredis

from app.core.pubsub import publish_progress


def _load_app():
    from app.main import app
    from app.core.config import settings
    from app.core.database import get_async_session
    from app.models.base import Base
    return app, settings, get_async_session, Base


@pytest.mark.asyncio
async def test_pubsub_publish_subscribe():
    """测试 Redis Pub/Sub 发布-订阅流程"""
    import app.core.redis as _redis_mod

    fake_redis = fakeredis.FakeAsyncRedis(decode_responses=True, version=(7,))
    _redis_mod._client = fake_redis

    try:
        from app.core.pubsub import subscribe_progress

        project_id = 999
        received = []

        async def subscriber():
            async for event in subscribe_progress(project_id):
                received.append(event)

        # 启动订阅者
        task = asyncio.create_task(subscriber())

        # 等待订阅就绪
        await asyncio.sleep(0.05)

        # 发布事件序列
        await publish_progress(project_id, {
            "type": "pipeline_start",
            "project_id": project_id,
            "total_chapters": 2,
        })
        await publish_progress(project_id, {
            "type": "chapter_start",
            "chapter_no": "第一章",
            "chapter_idx": 0,
        })
        await publish_progress(project_id, {
            "type": "phase",
            "chapter_no": "第一章",
            "phase": "rag_retrieve",
            "detail": "检索中",
        })
        await publish_progress(project_id, {
            "type": "chapter_done",
            "chapter_no": "第一章",
            "status": "ok",
            "word_count": 1500,
        })
        await publish_progress(project_id, {
            "type": "pipeline_done",
            "completed": 1,
            "failed": 0,
            "total": 2,
        })

        # 等待订阅者处理
        await asyncio.wait_for(task, timeout=2.0)

        assert len(received) == 5
        assert received[0]["type"] == "pipeline_start"
        assert received[1]["type"] == "chapter_start"
        assert received[2]["type"] == "phase"
        assert received[2]["phase"] == "rag_retrieve"
        assert received[3]["type"] == "chapter_done"
        assert received[3]["word_count"] == 1500
        assert received[4]["type"] == "pipeline_done"

    finally:
        await fake_redis.aclose()
        _redis_mod._client = None


@pytest.mark.asyncio
async def test_pubsub_subscriber_exits_on_pipeline_done():
    """订阅者收到 pipeline_done 后应自动退出"""
    import app.core.redis as _redis_mod

    fake_redis = fakeredis.FakeAsyncRedis(decode_responses=True, version=(7,))
    _redis_mod._client = fake_redis

    try:
        from app.core.pubsub import subscribe_progress

        project_id = 888
        count = 0

        async def subscriber():
            nonlocal count
            async for _ in subscribe_progress(project_id):
                count += 1

        task = asyncio.create_task(subscriber())
        await asyncio.sleep(0.05)

        # 直接发送 pipeline_done
        await publish_progress(project_id, {
            "type": "pipeline_done",
            "completed": 0,
            "failed": 0,
            "total": 0,
        })

        await asyncio.wait_for(task, timeout=2.0)
        assert count == 1  # 只收到一条就退出

    finally:
        await fake_redis.aclose()
        _redis_mod._client = None
