"""
企业能力画像 — 五维雷达图谱

维度:
  1. 硬件能力: 车辆、仓储、冷链覆盖
  2. 合规能力: 资质完备度、有效期健康度
  3. 服务能力: 配送覆盖、客户数、经营年限
  4. 文档能力: 章节编辑率、AI 生成接受度
  5. 竞争能力: 历史项目数、完成率

数据源（全部通过 Application 层独立查询，严禁联表）:
  - enterprise 表: 基础信息 → 硬件+服务
  - credential 表: 资质证照 → 合规
  - feedback_log 表: 用户修改 → 文档
  - bid_project 表: 历史项目 → 竞争

架构约束:
  - 所有 DB ���询强制绑定 tenant_id
  - 每个维度独立查询方法，在 build_profile 中聚合
  - 评分 0~100，整数
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enterprise import Enterprise
from app.models.credential import Credential
from app.models.bid_project import BidProject, BidChapter
from app.models.feedback import FeedbackLog

logger = logging.getLogger("freshbid.profile")

# ── 核心资质清单（有则加分） ─────────────────────────
_CORE_CREDENTIALS = [
    "food_license",     # 食品经营许可证
    "business_license", # 营业执照
    "haccp",            # HACCP
    "iso22000",         # ISO 22000
    "sc",               # SC 认证
]


# ── 数据模型 ─────────────────────────────────────────

@dataclass
class DimensionScore:
    """单维度评分"""
    name: str
    score: int          # 0~100
    details: dict = field(default_factory=dict)


@dataclass
class EnterpriseProfile:
    """完整企业画像"""
    enterprise_id: int
    enterprise_name: str
    generated_at: str = ""
    overall_score: int = 0
    dimensions: list[DimensionScore] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enterprise_id": self.enterprise_id,
            "enterprise_name": self.enterprise_name,
            "generated_at": self.generated_at,
            "overall_score": self.overall_score,
            "dimensions": [
                {"name": d.name, "score": d.score, "details": d.details}
                for d in self.dimensions
            ],
        }


@dataclass
class MatchResult:
    """企业能��� vs 招标要求匹配度"""
    enterprise_id: int
    project_id: int
    match_score: int    # 0~100
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)


# ── 画像服务 ─────────────────────────────────────────

class CapabilityProfileService:
    """企业能力画像构建服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def build_profile(
        self, enterprise_id: int, tenant_id: int
    ) -> EnterpriseProfile:
        """构建完整企业画像（五维度独立查���后聚合）"""
        # 加载企业基础信息
        enterprise = await self._load_enterprise(enterprise_id, tenant_id)
        if not enterprise:
            raise ValueError("企业不存在")

        profile = EnterpriseProfile(
            enterprise_id=enterprise_id,
            enterprise_name=enterprise.name,
            generated_at=datetime.now().isoformat(),
        )

        # 五个维度独立计算（每个维度独立查询���不联表）
        d1 = await self._score_hardware(enterprise)
        d2 = await self._score_compliance(enterprise_id, tenant_id, enterprise)
        d3 = self._score_service(enterprise)
        d4 = await self._score_documentation(enterprise_id, tenant_id)
        d5 = await self._score_competitiveness(enterprise_id, tenant_id)

        profile.dimensions = [d1, d2, d3, d4, d5]
        profile.overall_score = round(
            sum(d.score for d in profile.dimensions) / len(profile.dimensions)
        )

        return profile

    async def match_score(
        self, enterprise_id: int, project_id: int, tenant_id: int
    ) -> MatchResult:
        """企业能力 vs 招标要求匹配度评分"""
        profile = await self.build_profile(enterprise_id, tenant_id)

        # 加载项目要求
        project = await self._load_project(project_id, tenant_id)
        if not project:
            raise ValueError("项目不存在")

        strengths = []
        weaknesses = []

        for dim in profile.dimensions:
            if dim.score >= 70:
                strengths.append(f"{dim.name}优秀（{dim.score}分）")
            elif dim.score < 40:
                weaknesses.append(f"{dim.name}不足（{dim.score}分），建议加强")

        # 匹配度 = 画像总分 × 要求覆��系数
        req_count = len(project.requirements) if project.requirements else 0
        coverage_factor = min(1.0, 0.7 + req_count * 0.03) if req_count else 0.8
        match = round(profile.overall_score * coverage_factor)

        return MatchResult(
            enterprise_id=enterprise_id,
            project_id=project_id,
            match_score=min(match, 100),
            strengths=strengths,
            weaknesses=weaknesses,
        )

    # ── 维度1: 硬件能力 ──────────────────────────────

    async def _score_hardware(self, ent: Enterprise) -> DimensionScore:
        """硬件能力评分: 车辆 + 仓储 + 冷链"""
        score = 0
        details = {}

        # 冷链车辆（0~30分）
        vehicles = ent.cold_chain_vehicles or 0
        normal = ent.normal_vehicles or 0
        total_vehicles = vehicles + normal
        details["cold_chain_vehicles"] = vehicles
        details["normal_vehicles"] = normal
        if vehicles >= 10:
            score += 30
        elif vehicles >= 5:
            score += 20
        elif vehicles > 0:
            score += 10

        # 仓储面积（0~25分）
        warehouse = ent.warehouse_area or 0
        details["warehouse_area"] = warehouse
        if warehouse >= 5000:
            score += 25
        elif warehouse >= 2000:
            score += 18
        elif warehouse >= 500:
            score += 10
        elif warehouse > 0:
            score += 5

        # 冷库面积（0~25分）
        cold = ent.cold_storage_area or 0
        details["cold_storage_area"] = cold
        if cold >= 2000:
            score += 25
        elif cold >= 500:
            score += 18
        elif cold >= 100:
            score += 10
        elif cold > 0:
            score += 5

        # 温度范围（0~20分）
        if ent.cold_storage_temp:
            details["cold_storage_temp"] = ent.cold_storage_temp
            score += 20
        else:
            details["cold_storage_temp"] = None

        return DimensionScore(name="硬件能力", score=min(score, 100), details=details)

    # ── 维度2: 合规能力 ──────────────────────────────

    async def _score_compliance(
        self, enterprise_id: int, tenant_id: int, ent: Enterprise
    ) -> DimensionScore:
        """合规能力评分: 资质完备度 + 有效期健康度"""
        # 独立查询资质表
        result = await self.session.execute(
            select(Credential).where(
                Credential.enterprise_id == enterprise_id,
                Credential.tenant_id == tenant_id,
            )
        )
        credentials = list(result.scalars().all())

        score = 0
        details = {}
        now = datetime.now()

        # 资质完备度（0~60分）
        cred_types = {c.cred_type for c in credentials}
        owned = len(cred_types & set(_CORE_CREDENTIALS))
        completeness = owned / len(_CORE_CREDENTIALS) if _CORE_CREDENTIALS else 0
        details["credential_count"] = len(credentials)
        details["core_owned"] = owned
        details["core_total"] = len(_CORE_CREDENTIALS)
        details["completeness"] = round(completeness, 2)
        score += round(completeness * 60)

        # 企业自带认证标志
        if ent.haccp_certified:
            score += 5
        if ent.iso22000_certified:
            score += 5

        # 有效期健康度（0~30分）
        expired_count = 0
        soon_expire = 0
        for cred in credentials:
            if cred.is_permanent:
                continue
            if not cred.expiry_date:
                continue
            try:
                expiry = datetime.strptime(cred.expiry_date[:10], "%Y-%m-%d")
                days_left = (expiry - now).days
                if days_left < 0:
                    expired_count += 1
                elif days_left < 90:
                    soon_expire += 1
            except (ValueError, TypeError):
                continue

        details["expired"] = expired_count
        details["expiring_soon"] = soon_expire
        # 有效期健康度（0~30分）— 仅在有资质时评分，无资质不给分
        if credentials:
            if expired_count == 0 and soon_expire == 0:
                score += 30
            elif expired_count == 0:
                score += 15
            # 有过期的不加分

        return DimensionScore(name="合规能力", score=min(score, 100), details=details)

    # ── 维度3: 服务能力 ──────────────────────────────

    def _score_service(self, ent: Enterprise) -> DimensionScore:
        """服务能力评分: 客户数 + 员工 + 经营年限 + 营收"""
        score = 0
        details = {}

        # 服务客户数（0~25分）
        customers = ent.service_customers or 0
        details["service_customers"] = customers
        if customers >= 50:
            score += 25
        elif customers >= 20:
            score += 18
        elif customers >= 5:
            score += 10
        elif customers > 0:
            score += 5

        # 员工人数（0~25分）
        employees = ent.employee_count or 0
        details["employee_count"] = employees
        if employees >= 200:
            score += 25
        elif employees >= 50:
            score += 18
        elif employees >= 10:
            score += 10
        elif employees > 0:
            score += 5

        # 经营年限（0~25分）
        years = 0
        if ent.established_date:
            try:
                est = datetime.strptime(ent.established_date[:10], "%Y-%m-%d")
                years = (datetime.now() - est).days // 365
            except (ValueError, TypeError):
                pass
        details["years_established"] = years
        if years >= 10:
            score += 25
        elif years >= 5:
            score += 18
        elif years >= 3:
            score += 10
        elif years > 0:
            score += 5

        # 年营收（0~25分）
        revenue = 0
        if ent.annual_revenue:
            try:
                revenue = float(ent.annual_revenue)
            except (ValueError, TypeError):
                pass
        details["annual_revenue"] = revenue
        if revenue >= 5000:
            score += 25
        elif revenue >= 1000:
            score += 18
        elif revenue >= 200:
            score += 10
        elif revenue > 0:
            score += 5

        return DimensionScore(name="服务能力", score=min(score, 100), details=details)

    # ── 维度4: 文档能力 ──────────────────────────────

    async def _score_documentation(
        self, enterprise_id: int, tenant_id: int
    ) -> DimensionScore:
        """文档能力评分: 反馈行为统计（独立查询 feedback_log）"""
        # 通过 bid_project 关联 enterprise_id 找到项目列表
        proj_result = await self.session.execute(
            select(BidProject.id).where(
                BidProject.enterprise_id == enterprise_id,
                BidProject.tenant_id == tenant_id,
            )
        )
        project_ids = [row[0] for row in proj_result.fetchall()]

        details = {"project_count": len(project_ids)}

        if not project_ids:
            return DimensionScore(name="文档能力", score=50, details=details)

        # 独立查询反馈统计
        fb_result = await self.session.execute(
            select(
                FeedbackLog.action,
                func.count(),
                func.avg(FeedbackLog.diff_ratio),
            ).where(
                FeedbackLog.project_id.in_(project_ids),
                FeedbackLog.tenant_id == tenant_id,
            ).group_by(FeedbackLog.action)
        )
        fb_stats = {row[0]: {"count": row[1], "avg_diff": row[2]} for row in fb_result.fetchall()}

        accept_count = fb_stats.get("accept", {}).get("count", 0)
        edit_count = fb_stats.get("edit", {}).get("count", 0)
        reject_count = fb_stats.get("reject", {}).get("count", 0)
        total = accept_count + edit_count + reject_count

        details["accept"] = accept_count
        details["edit"] = edit_count
        details["reject"] = reject_count
        details["avg_diff_ratio"] = round(float(fb_stats.get("edit", {}).get("avg_diff", 0) or 0), 4)

        score = 50  # 基线分

        if total > 0:
            # 接受率越高 → 文档能力越强（+30分）
            accept_ratio = accept_count / total
            score += round(accept_ratio * 30)

            # 编辑差异度低 → AI 生���质量高（+20分）
            avg_diff = details["avg_diff_ratio"]
            if avg_diff < 0.1:
                score += 20
            elif avg_diff < 0.3:
                score += 10

        return DimensionScore(name="文档能力", score=min(score, 100), details=details)

    # ── 维度5: 竞争能力 ──────────────────────────────

    async def _score_competitiveness(
        self, enterprise_id: int, tenant_id: int
    ) -> DimensionScore:
        """竞争能力评分: 历史项目数 + 完成率"""
        # 独立查询项目统计
        result = await self.session.execute(
            select(BidProject.status, func.count()).where(
                BidProject.enterprise_id == enterprise_id,
                BidProject.tenant_id == tenant_id,
            ).group_by(BidProject.status)
        )
        status_counts = {row[0]: row[1] for row in result.fetchall()}

        total = sum(status_counts.values())
        completed = status_counts.get("completed", 0) + status_counts.get("submitted", 0)
        won = status_counts.get("won", 0)

        details = {
            "total_projects": total,
            "completed": completed,
            "won": won,
            "completion_rate": round(completed / total, 2) if total else 0,
            "win_rate": round(won / completed, 2) if completed else 0,
        }

        score = 0

        # 项目经验（0~40分）
        if total >= 20:
            score += 40
        elif total >= 10:
            score += 30
        elif total >= 5:
            score += 20
        elif total > 0:
            score += 10

        # 完成率（0~30分）
        if total > 0:
            comp_rate = completed / total
            score += round(comp_rate * 30)

        # 中标率（0~30分）
        if completed > 0:
            win_rate = won / completed
            score += round(win_rate * 30)

        return DimensionScore(name="竞争能力", score=min(score, 100), details=details)

    # ── 数据加载（Application 层隔离）────���───────────

    async def _load_enterprise(
        self, enterprise_id: int, tenant_id: int
    ) -> Optional[Enterprise]:
        result = await self.session.execute(
            select(Enterprise).where(
                Enterprise.id == enterprise_id,
                Enterprise.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def _load_project(
        self, project_id: int, tenant_id: int
    ) -> Optional[BidProject]:
        result = await self.session.execute(
            select(BidProject).where(
                BidProject.id == project_id,
                BidProject.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()
