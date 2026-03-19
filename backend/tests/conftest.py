"""
pytest 测试基础设施 — conftest.py

核心策略:
  - 在测试的事件循环中创建新的 async engine + session factory
  - 通过 dependency_overrides 替换 app 的 get_async_session
  - 避免 asyncpg 连接池跨事件循环复用导致的 InterfaceError
"""
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.main import app
from app.core.config import settings
from app.core.database import get_async_session
from app.models.base import Base


# 每个测试函数创建一次，确保 engine 绑定在当前事件循环
@pytest_asyncio.fixture
async def async_client():
    """异步 HTTP 客户端 — 在当前事件循环创建独立 DB engine"""
    # 创建绑定本次事件循环的 engine（避免跨循环 InterfaceError）
    test_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=5,
    )

    # 自动同步所有表结构（含新模块），确保测试 DB 与代码保持一致
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    test_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Override FastAPI 的 DB session 依赖
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

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # 清理: 恢复原始依赖 + 关闭测试 engine
    app.dependency_overrides.pop(get_async_session, None)
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
