"""
Redis 异步客户端 — 连接池管理
"""
import logging
from redis.asyncio import Redis, ConnectionPool
from app.core.config import settings

logger = logging.getLogger("freshbid")

_pool: ConnectionPool | None = None
_client: Redis | None = None


async def init_redis() -> Redis:
    """应用启动时调用：创建连接池并返回 Redis 客户端"""
    global _pool, _client
    _pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    _client = Redis(connection_pool=_pool)
    await _client.ping()
    logger.info("Redis 连接池已初始化: %s", settings.REDIS_URL)
    return _client


async def close_redis() -> None:
    """应用关闭时调用：释放连接池"""
    global _pool, _client
    if _client:
        await _client.aclose()
        _client = None
    if _pool:
        await _pool.aclose()
        _pool = None
    logger.info("Redis 连接池已关闭")


def get_redis() -> Redis:
    """获取 Redis 客户端单例（供依赖注入或直接调用）"""
    if _client is None:
        raise RuntimeError("Redis 尚未初始化，请先调用 init_redis()")
    return _client
