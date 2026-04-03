"""
资质到期预警服务

功能:
  1. 日常预警: 扫描企业全部资质，按到期天数分级（红/橙/黄/绿）
  2. 投标拦截: 检查指定项目要求的资质在开标日是否仍然有效
  3. 输出结构化报告供前端仪表盘展示

架构红线:
  - 纯日期计算，不调用 LLM
  - tenant_id 强制绑定
"""
import logging
from datetime import date, datetime
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.credential import Credential

logger = logging.getLogger("freshbid")


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class CredentialAlert:
    """单条资质预警"""
    credential_id: int
    cred_name: str
    cred_type: str
    cred_no: Optional[str]
    expiry_date: Optional[str]        # YYYY-MM-DD
    days_remaining: Optional[int]     # None = 永久有效
    level: str                        # expired / red / orange / yellow / green
    message: str


@dataclass
class CredentialAlertReport:
    """资质预警报告"""
    enterprise_id: int
    total_credentials: int = 0
    expired_count: int = 0
    warning_count: int = 0            # red + orange + yellow
    alerts: list[CredentialAlert] = field(default_factory=list)
    can_bid: bool = True              # False = 有过期资质，建议暂停投标


# ── 日期工具 ──────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """解析日期字符串，支持 YYYY-MM-DD 和 YYYY/MM/DD"""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _classify_alert(days_remaining: int) -> tuple[str, str]:
    """根据剩余天数分级

    Returns:
        (level, message)
    """
    if days_remaining < 0:
        return "expired", f"已过期 {abs(days_remaining)} 天，请立即续期"
    if days_remaining <= 30:
        return "red", f"将在 {days_remaining} 天内到期，请紧急处理"
    if days_remaining <= 60:
        return "orange", f"将在 {days_remaining} 天内到期，请尽快安排续期"
    if days_remaining <= settings.CREDENTIAL_EXPIRY_WARN_DAYS:
        return "yellow", f"将在 {days_remaining} 天内到期，建议提前准备"
    return "green", "有效期充足"


# ── 主服务 ────────────────────────────────────────────────

class CredentialAlertService:
    """资质到期预警服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def scan_enterprise(
        self,
        enterprise_id: int,
        tenant_id: int,
        reference_date: Optional[date] = None,
    ) -> CredentialAlertReport:
        """扫描企业全部资质的到期状态

        Args:
            enterprise_id: 企业 ID
            tenant_id: 租户 ID
            reference_date: 参考日期（默认今天，投标时传入开标日）

        Returns:
            资质预警报告
        """
        ref_date = reference_date or date.today()

        result = await self.session.execute(
            select(Credential).where(
                Credential.enterprise_id == enterprise_id,
                Credential.tenant_id == tenant_id,
            )
        )
        credentials = list(result.scalars().all())

        report = CredentialAlertReport(
            enterprise_id=enterprise_id,
            total_credentials=len(credentials),
        )

        for cred in credentials:
            if cred.is_permanent:
                report.alerts.append(CredentialAlert(
                    credential_id=cred.id,
                    cred_name=cred.cred_name,
                    cred_type=cred.cred_type,
                    cred_no=cred.cred_no,
                    expiry_date=None,
                    days_remaining=None,
                    level="green",
                    message="长期有效",
                ))
                continue

            exp_date = _parse_date(cred.expiry_date)
            if exp_date is None:
                report.alerts.append(CredentialAlert(
                    credential_id=cred.id,
                    cred_name=cred.cred_name,
                    cred_type=cred.cred_type,
                    cred_no=cred.cred_no,
                    expiry_date=cred.expiry_date,
                    days_remaining=None,
                    level="yellow",
                    message="到期日期未填写，请补充",
                ))
                report.warning_count += 1
                continue

            days_remaining = (exp_date - ref_date).days
            level, message = _classify_alert(days_remaining)

            report.alerts.append(CredentialAlert(
                credential_id=cred.id,
                cred_name=cred.cred_name,
                cred_type=cred.cred_type,
                cred_no=cred.cred_no,
                expiry_date=cred.expiry_date,
                days_remaining=days_remaining,
                level=level,
                message=message,
            ))

            if level == "expired":
                report.expired_count += 1
                report.can_bid = False
            elif level in ("red", "orange", "yellow"):
                report.warning_count += 1

        # 按紧急程度排序：expired > red > orange > yellow > green
        level_order = {"expired": 0, "red": 1, "orange": 2, "yellow": 3, "green": 4}
        report.alerts.sort(key=lambda a: (level_order.get(a.level, 5), a.days_remaining or 9999))

        return report

    async def check_bid_readiness(
        self,
        enterprise_id: int,
        tenant_id: int,
        bid_open_date: Optional[str] = None,
        required_cred_types: Optional[list[str]] = None,
    ) -> CredentialAlertReport:
        """投标前资质有效期拦截检查

        Args:
            enterprise_id: 企业 ID
            tenant_id: 租户 ID
            bid_open_date: 开标日期（YYYY-MM-DD），不填则用今天
            required_cred_types: 该项目要求的资质类型列表

        Returns:
            资质预警报告（can_bid=False 时应阻止投标）
        """
        ref_date = _parse_date(bid_open_date) or date.today()
        report = await self.scan_enterprise(enterprise_id, tenant_id, ref_date)

        # 如果指定了必须的资质类型，检查是否齐全
        if required_cred_types:
            existing_types = {a.cred_type for a in report.alerts}
            missing = set(required_cred_types) - existing_types
            for cred_type in missing:
                report.alerts.insert(0, CredentialAlert(
                    credential_id=0,
                    cred_name=f"缺失: {cred_type}",
                    cred_type=cred_type,
                    cred_no=None,
                    expiry_date=None,
                    days_remaining=None,
                    level="expired",
                    message=f"项目要求的 {cred_type} 资质缺失，请尽快补办",
                ))
                report.expired_count += 1
                report.can_bid = False

        return report
