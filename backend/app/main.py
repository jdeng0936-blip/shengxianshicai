"""
FastAPI 应用入口
"""
import logging
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.config import settings

# ========== 结构化日志配置 ==========
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("freshbid")

# 关闭 pdfminer 的 DEBUG 日志刷屏（解析 PDF 时会产生海量输出）
logging.getLogger("pdfminer").setLevel(logging.WARNING)

from app.core.database import engine, async_session_factory
from app.core.redis import init_redis, close_redis
from app.models.base import Base

# 导入所有模型，确保 SQLAlchemy 注册全部表
# ---- 系统模型 ----
from app.models.user import SysUser, SysRole  # noqa: F401
from app.models.chat import *  # noqa: F401,F403
# ---- 投标业务模型 ----
from app.models.enterprise import *  # noqa: F401,F403
from app.models.bid_project import *  # noqa: F401,F403
from app.models.credential import *  # noqa: F401,F403
from app.models.quotation import *  # noqa: F401,F403
from app.models.image_asset import *  # noqa: F401,F403
from app.models.billing import *  # noqa: F401,F403
from app.models.feedback import *  # noqa: F401,F403
from app.models.tender_notice import *  # noqa: F401,F403
from app.models.bid_review import *  # noqa: F401,F403
from app.models.payment import *  # noqa: F401,F403

# ---- API 路由 ----
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.ai import router as ai_router
from app.api.v1.chat import router as chat_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.system import router as system_router
# ---- 投标业务路由 ----
from app.api.v1.enterprise import router as enterprise_router
from app.api.v1.bid_project import router as bid_project_router
from app.api.v1.credential import router as credential_router
from app.api.v1.quotation import router as quotation_router
from app.api.v1.image_asset import router as image_asset_router
from app.api.v1.standard import router as standard_router
from app.api.v1.billing import router as billing_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.tender_notice import router as tender_notice_router
from app.api.v1.bid_review import router as bid_review_router
from app.api.v1.payment import router as payment_router


async def _init_db():
    """自动建表 + 种子数据（仅在表不存在时执行）"""
    import bcrypt as _bcrypt

    # 建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库表结构同步完成")

    # 种子数据：admin 用户
    # 管理员初始密码从环境变量读取，避免硬编码（安全红线）
    import os as _os
    _admin_password = _os.environ.get("ADMIN_INIT_PASSWORD", "admin123")

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
                admin_role = SysRole(name="管理员", description="系统管理员", tenant_id=1, created_by=0)
                session.add(admin_role)
                await session.flush()

            # 创建 admin 用户（密码从 ADMIN_INIT_PASSWORD 环境变量读取）
            admin_user = SysUser(
                username="admin",
                hashed_password=_bcrypt.hashpw(_admin_password.encode(), _bcrypt.gensalt()).decode(),
                real_name="系统管理员",
                role_id=admin_role.id,
                is_active=True,
                tenant_id=1,
                created_by=0,
            )
            session.add(admin_user)
            await session.commit()
            print("✅ 默认管理员账号创建完成 (admin / ***)")
            if _admin_password == "admin123":
                print("⚠️ 警告: 正在使用默认密码 admin123，请尽快通过系统修改密码或设置 ADMIN_INIT_PASSWORD 环境变量")
        else:
            print("ℹ️ admin 用户已存在，跳过种子数据")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # --- 启动时 ---
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
    await _init_db()
    await init_redis()
    yield
    # --- 关闭时 ---
    print("🛑 应用关闭，释放资源...")
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="鲜标智投 — 生鲜食材配送投标智能平台 API",
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

# --- 全局异常处理 ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """未捕获异常统一返回 JSON 格式，避免暴露堆栈"""
    logger.error(f"未处理异常 | {request.method} {request.url.path} | {type(exc).__name__}: {exc}")
    if settings.DEBUG:
        logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误", "data": None},
    )


# --- 请求耗时日志 ---
@app.middleware("http")
async def log_request_time(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 1)
    if duration > 1000:  # 慢请求（>1s）告警
        logger.warning(f"慢请求 | {request.method} {request.url.path} | {duration}ms")
    elif not request.url.path.startswith("/api/v1/health"):
        logger.info(f"{request.method} {request.url.path} | {response.status_code} | {duration}ms")
    return response


# --- 注册路由 ---
app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(system_router, prefix="/api/v1")
# ---- 投标业务 ----
app.include_router(enterprise_router, prefix="/api/v1")
app.include_router(bid_project_router, prefix="/api/v1")
app.include_router(credential_router, prefix="/api/v1")
app.include_router(quotation_router, prefix="/api/v1")
app.include_router(image_asset_router, prefix="/api/v1")
app.include_router(standard_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")
app.include_router(feedback_router, prefix="/api/v1")
app.include_router(tender_notice_router, prefix="/api/v1")
app.include_router(bid_review_router, prefix="/api/v1")
app.include_router(payment_router, prefix="/api/v1")
