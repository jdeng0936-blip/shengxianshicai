"""
Redis 任务存储 — 替代内存字典，提供 TTL 防护和分布式锁
"""
import json
import logging
from typing import Optional

from redis.asyncio import Redis

logger = logging.getLogger("freshbid")

# Key 前缀
_PREVIEW_PREFIX = "parse_task:"
_FULLPARSE_LOCK_PREFIX = "fullparse_lock:"
_FULLPARSE_STATE_PREFIX = "fullparse_state:"

# TTL 常量（秒）
PREVIEW_TASK_TTL = 3600        # 预览解析结果保留 1 小时
FULLPARSE_LOCK_TTL = 600       # 全量解析锁 10 分钟（超时自动释放）
FULLPARSE_STATE_TTL = 1800     # 全量解析状态保留 30 分钟


class ParseTaskStore:
    """预览解析任务的 Redis 存储，替代 _parse_tasks 内存字典"""

    def __init__(self, redis: Redis):
        self._r = redis

    async def create(self, task_id: str) -> None:
        """注册新任务，状态为 pending"""
        payload = json.dumps({"status": "pending", "data": None, "error": None})
        await self._r.set(f"{_PREVIEW_PREFIX}{task_id}", payload, ex=PREVIEW_TASK_TTL)

    async def set_done(self, task_id: str, data: dict) -> None:
        """标记任务完成，写入结果"""
        payload = json.dumps({"status": "done", "data": data, "error": None})
        await self._r.set(f"{_PREVIEW_PREFIX}{task_id}", payload, ex=PREVIEW_TASK_TTL)

    async def set_error(self, task_id: str, error: str) -> None:
        """标记任务失败"""
        payload = json.dumps({"status": "error", "data": None, "error": error})
        await self._r.set(f"{_PREVIEW_PREFIX}{task_id}", payload, ex=PREVIEW_TASK_TTL)

    async def get(self, task_id: str) -> Optional[dict]:
        """查询任务状态，不存在返回 None"""
        raw = await self._r.get(f"{_PREVIEW_PREFIX}{task_id}")
        if raw is None:
            return None
        return json.loads(raw)


class FullParseGuard:
    """
    全量解析的状态管理与防重入锁。

    - acquire(): 用 SETNX 获取分布式锁，防止同一项目重复触发解析
    - set_state(): 记录解析进度（parsing / parsed / failed）
    - release(): 释放锁
    - 所有 key 带 TTL，即使进程崩溃也不会死锁
    """

    def __init__(self, redis: Redis, project_id: int):
        self._r = redis
        self._lock_key = f"{_FULLPARSE_LOCK_PREFIX}{project_id}"
        self._state_key = f"{_FULLPARSE_STATE_PREFIX}{project_id}"

    async def acquire(self) -> bool:
        """尝试获取解析锁，成功返回 True"""
        acquired = await self._r.set(
            self._lock_key, "locked", nx=True, ex=FULLPARSE_LOCK_TTL
        )
        if acquired:
            logger.info("获取全量解析锁: %s", self._lock_key)
        else:
            logger.warning("全量解析锁已存在（解析进行中）: %s", self._lock_key)
        return bool(acquired)

    async def set_state(self, status: str, detail: str = "") -> None:
        """记录解析状态到 Redis"""
        payload = json.dumps({"status": status, "detail": detail})
        await self._r.set(self._state_key, payload, ex=FULLPARSE_STATE_TTL)

    async def get_state(self) -> Optional[dict]:
        """查询当前解析状态"""
        raw = await self._r.get(self._state_key)
        if raw is None:
            return None
        return json.loads(raw)

    async def release(self) -> None:
        """释放锁"""
        await self._r.delete(self._lock_key)
        logger.info("释放全量解析锁: %s", self._lock_key)
