"""
计费服务 — 配额检查 + 用量记录

MVP 阶段：
  - 免费用户: 5 个项目 / 10 次导出 / 100 次 AI 调用
  - 管理员可手动调整配额
  - 所有消耗操作记录到 usage_log
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import UserQuota, UsageLog

# 默认免费配额
DEFAULT_QUOTA = {
    "max_projects": 5,
    "max_exports": 10,
    "max_ai_calls": 100,
    "plan_type": "free",
}


class BillingService:
    """计费服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_quota(self, user_id: int, tenant_id: int) -> UserQuota:
        """获取用户配额（不存在则自动创建免费配额）"""
        result = await self.session.execute(
            select(UserQuota).where(
                UserQuota.user_id == user_id,
                UserQuota.tenant_id == tenant_id,
            )
        )
        quota = result.scalar_one_or_none()
        if not quota:
            quota = UserQuota(
                user_id=user_id,
                tenant_id=tenant_id,
                created_by=user_id,
                **DEFAULT_QUOTA,
            )
            self.session.add(quota)
            await self.session.flush()
        return quota

    async def check_quota(self, user_id: int, tenant_id: int, action: str) -> dict:
        """检查用户是否有足够配额

        Returns:
            {"allowed": bool, "remaining": int, "message": str}
        """
        quota = await self.get_or_create_quota(user_id, tenant_id)

        checks = {
            "create_project": (quota.used_projects, quota.max_projects, "项目"),
            "export_doc": (quota.used_exports, quota.max_exports, "导出"),
            "ai_generate": (quota.used_ai_calls, quota.max_ai_calls, "AI调用"),
            "ai_rewrite": (quota.used_ai_calls, quota.max_ai_calls, "AI调用"),
            "compliance_check": (quota.used_ai_calls, quota.max_ai_calls, "AI调用"),
        }

        if action not in checks:
            return {"allowed": True, "remaining": -1, "message": "无需配额"}

        used, max_val, label = checks[action]
        remaining = max_val - used

        if remaining <= 0:
            return {
                "allowed": False,
                "remaining": 0,
                "message": f"{label}配额已用完（{used}/{max_val}），请升级套餐",
            }

        return {
            "allowed": True,
            "remaining": remaining,
            "message": f"{label}剩余 {remaining} 次",
        }

    async def record_usage(
        self, user_id: int, tenant_id: int, action: str, resource_id: int = None, detail: str = ""
    ):
        """记录用量 + 扣减配额"""
        quota = await self.get_or_create_quota(user_id, tenant_id)

        # 扣减
        if action == "create_project":
            quota.used_projects += 1
        elif action == "export_doc":
            quota.used_exports += 1
        elif action in ("ai_generate", "ai_rewrite", "compliance_check"):
            quota.used_ai_calls += 1

        # 记录日志
        log = UsageLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource_id=resource_id,
            detail=detail,
            created_by=user_id,
        )
        self.session.add(log)
        await self.session.flush()

    async def get_usage_stats(self, user_id: int, tenant_id: int) -> dict:
        """获取用户用量统计"""
        quota = await self.get_or_create_quota(user_id, tenant_id)
        return {
            "plan_type": quota.plan_type,
            "projects": {"used": quota.used_projects, "max": quota.max_projects},
            "exports": {"used": quota.used_exports, "max": quota.max_exports},
            "ai_calls": {"used": quota.used_ai_calls, "max": quota.max_ai_calls},
        }
