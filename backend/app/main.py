"""
FastAPI 应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.config import settings
from app.core.database import engine, async_session_factory
from app.models.base import Base

# 导入所有模型，确保 SQLAlchemy 注册全部表
from app.models.user import SysUser, SysRole  # noqa: F401
from app.models.project import *  # noqa: F401,F403
from app.models.standard import *  # noqa: F401,F403
from app.models.rule import *  # noqa: F401,F403
from app.models.document import *  # noqa: F401,F403
from app.models.mine import *  # noqa: F401,F403
from app.models.drawing import *  # noqa: F401,F403

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.project import router as project_router
from app.api.v1.standard import router as standard_router
from app.api.v1.rule import router as rule_router
from app.api.v1.rule import match_router
from app.api.v1.calc import router as calc_router
from app.api.v1.doc import router as doc_router
from app.api.v1.ai import router as ai_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.drawing import router as drawing_router


async def _init_db():
    """自动建表 + 种子数据（仅在表不存在时执行）"""
    import bcrypt as _bcrypt

    # 建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库表结构同步完成")

    # 种子数据：admin 用户
    async with async_session_factory() as session:
        result = await session.execute(
            select(SysUser).where(SysUser.username == "admin")
        )
        if not result.scalar_one_or_none():
            # 获取或创建默认角色
            role_result = await session.execute(
                select(SysRole).where(SysRole.name == "管理员")
            )
            admin_role = role_result.scalar_one_or_none()
            if not admin_role:
                admin_role = SysRole(name="管理员", description="系统管理员")
                session.add(admin_role)
                await session.flush()

            # 创建 admin 用户（密码: admin123）
            admin_user = SysUser(
                username="admin",
                hashed_password=_bcrypt.hashpw("admin123".encode(), _bcrypt.gensalt()).decode(),
                real_name="系统管理员",
                role_id=admin_role.id,
                is_active=True,
                tenant_id=1,
                created_by=0,
            )
            session.add(admin_user)
            await session.commit()
            print("✅ 默认管理员账号创建完成 (admin / admin123)")
        else:
            print("ℹ️ admin 用户已存在，跳过种子数据")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # --- 启动时 ---
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    await _init_db()
    yield
    # --- 关闭时 ---
    print("🛑 应用关闭，释放资源...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="煤矿掘进工作面作业规程智能生成平台 API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# --- CORS 中间件 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 注册路由 ---
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(project_router, prefix="/api/v1")
app.include_router(standard_router, prefix="/api/v1")
app.include_router(rule_router, prefix="/api/v1")
app.include_router(match_router, prefix="/api/v1")
app.include_router(calc_router, prefix="/api/v1")
app.include_router(doc_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(drawing_router, prefix="/api/v1")

# TODO: 后续逐步注册
# app.include_router(system_router, prefix="/api/v1")

