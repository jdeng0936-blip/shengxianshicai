"""
健康检查路由 — 无需认证
"""
from fastapi import APIRouter

router = APIRouter(tags=["系统"])


@router.get("/health")
async def health_check():
    """健康检查接口，用于运维探活"""
    return {"status": "ok", "service": "fresh-food-bidding-api"}
