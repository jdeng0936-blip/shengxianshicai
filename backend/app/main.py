"""
FastAPI 应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # --- 启动时 ---
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")
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

# TODO: 后续逐步注册
# app.include_router(drawing_router, prefix="/api/v1")
# app.include_router(system_router, prefix="/api/v1")
