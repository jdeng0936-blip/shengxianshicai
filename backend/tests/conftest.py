"""
pytest 测试基础设施 — conftest.py

核心策略:
  - 在测试的事件循环中创建新的 async engine + session factory
  - 通过 dependency_overrides 替换 app 的 get_async_session
  - 避免 asyncpg 连接池跨事件循环复用导致的 InterfaceError
  - 延迟导入 app，避免 collect 阶段触发 Settings 校验失败
  - 使用 fakeredis 替代真实 Redis，保持测试隔离
"""
import os

# ── 测试环境变量注入（必须在任何 app 模块导入前执行）──
# config.py 模块级别实例化 Settings()，会校验 SECRET_KEY 非默认值
# 此处提前注入测试专用值，跳过生产安全检查
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production-use-32c")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_ci.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DEBUG", "true")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
import fakeredis


def _load_app():
    """延迟导入 app 及其依赖，仅在 fixture 实际执行时触发"""
    from app.main import app
    from app.core.config import settings
    from app.core.database import get_async_session
    from app.models.base import Base
    return app, settings, get_async_session, Base


@pytest_asyncio.fixture
async def async_client():
    """异步 HTTP 客户端 — 在当前事件循环创建独立 DB engine"""
    app, settings, get_async_session, Base = _load_app()

    test_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=5,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 种子数据：幂等创建 admin 角色 + admin 用户（登录测试依赖）
    from sqlalchemy import select
    from app.core.security import get_password_hash
    from app.models.user import SysUser, SysRole
    seed_session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with seed_session_factory() as seed_session:
        existing = (await seed_session.execute(select(SysRole).where(SysRole.id == 1))).scalar_one_or_none()
        if not existing:
            role = SysRole(id=1, name="管理员", description="系统管理员", tenant_id=1, created_by=1)
            seed_session.add(role)
            await seed_session.flush()
            admin = SysUser(
                id=1, username="admin",
                hashed_password=get_password_hash("admin123"),
                real_name="测试管理员", role_id=1, is_active=True,
                tenant_id=1, created_by=1,
            )
            seed_session.add(admin)
            await seed_session.commit()

    test_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_session():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_async_session] = override_get_session

    # 用 fakeredis 替换真实 Redis，保持测试隔离
    import app.core.redis as _redis_mod
    fake_redis = fakeredis.FakeAsyncRedis(decode_responses=True, version=(7,))
    _redis_mod._client = fake_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # 清理
    app.dependency_overrides.pop(get_async_session, None)
    await fake_redis.aclose()
    _redis_mod._client = None
    await test_engine.dispose()


@pytest_asyncio.fixture
async def auth_headers(async_client: AsyncClient) -> dict:
    """登录 admin 获取 JWT，返回带 Authorization 的请求头"""
    resp = await async_client.post("/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin123",
    })
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
