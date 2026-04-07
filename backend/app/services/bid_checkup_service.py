"""
一键投标体检聚合服务 — W4-D1

聚合已有的 5 大检查服务，提供单一入口 + 统一报告。
核心原则: 零新业务逻辑，只做编排 + 结果转换。

聚合对象（全部已存在）:
  1. CredentialAlertService    — 资质有效期扫描
  2. BidComplianceService      — 废标/资格/评分覆盖/数据一致性
  3. RiskReportService         — 综合风险报告
  4. review_scoring_coverage   — 评分覆盖率热力图
  5. compliance_gate           — 跨章节一致性 + 资质引用

输出: BidCheckupReport
  - 五维度统一评分（0~100）
  - 总分 + 通过/警告/致命计数
  - 每个维度的跳转链接（deeplink）+ 修复建议

架构约束:
  - 所有底层查询通过已有 service，严禁重写业务逻辑
  - tenant_id 强制隔离（调用层已保证）
  - 任何子检查失败不阻塞整体流程，降级为 "error" 状态
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bid_project import BidProject

logger = logging.getLogger("freshbid.checkup")


# ── 数据模型 ─────────────────────────────────────────

@dataclass
class CheckupDimension:
    """单维度体检结果"""
    name: str                          # "资质有效期" 等
    score: int                         # 0~100
    status: str                        # "passed" / "warning" / "failed" / "error"
    summary: str                       # 一句话结论
    issue_count: int = 0               # 问题数量
    details: dict = field(default_factory=dict)  # 子服务原始返回
    deeplink: str = ""                 # 前端跳转路径


@dataclass
class BidCheckupReport:
    """完整投标体检报告"""
    project_id: int
    project_name: str = ""
    generated_at: str = ""
    overall_score: int = 0             # 五维度加权平均
    overall_status: str = "passed"     # 整体状态
    dimensions: list[CheckupDimension] = field(default_factory=list)
    can_submit: bool = True            # 有 failed 维度时为 False
    fatal_count: int = 0               # 所有维度的 fatal/failed 总数
    warning_count: int = 0             # 所有维度的 warning 总数

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "generated_at": self.generated_at,
            "overall_score": self.overall_score,
            "overall_status": self.overall_status,
            "can_submit": self.can_submit,
            "fatal_count": self.fatal_count,
            "warning_count": self.warning_count,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "status": d.status,
                    "summary": d.summary,
                    "issue_count": d.issue_count,
                    "deeplink": d.deeplink,
                }
                for d in self.dimensions
            ],
        }


# ── 聚合服务 ─────────────────────────────────────────

class BidCheckupService:
    """一键投标体检聚合服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def run_checkup(
        self, project_id: int, tenant_id: int
    ) -> BidCheckupReport:
        """执行全量五维度体检

        流程: 并行调用 5 个子检查 → 聚合评分 → 统一报告
        任一子检查失败降级为 error，不阻断整体流程。
        """
        # 加载项目（tenant_id 强制隔离）
        project = await self._load_project(project_id, tenant_id)
        if not project:
            raise ValueError("项目不存在或无权访问")

        report = BidCheckupReport(
            project_id=project_id,
            project_name=project.project_name or "",
            generated_at=datetime.now().isoformat(),
        )

        # 五维度独立调用，任一失败降级
        dimensions = [
            await self._check_credentials(project, tenant_id),
            await self._check_compliance(project_id, tenant_id),
            await self._check_risk_report(project_id, tenant_id),
            await self._check_scoring_coverage(project_id, tenant_id),
            await self._check_consistency(project_id, tenant_id),
        ]
        report.dimensions = dimensions

        # 聚合总分与状态
        valid_scores = [d.score for d in dimensions if d.status != "error"]
        report.overall_score = (
            round(sum(valid_scores) / len(valid_scores)) if valid_scores else 0
        )

        for d in dimensions:
            if d.status == "failed":
                report.fatal_count += d.issue_count
                report.can_submit = False
            elif d.status == "warning":
                report.warning_count += d.issue_count

        if report.fatal_count > 0:
            report.overall_status = "failed"
        elif report.warning_count > 0:
            report.overall_status = "warning"
        else:
            report.overall_status = "passed"

        return report

    # ── 维度1: 资质有效期 ────────────────────────────

    async def _check_credentials(
        self, project: BidProject, tenant_id: int
    ) -> CheckupDimension:
        """调用 CredentialAlertService.check_bid_readiness()"""
        dim = CheckupDimension(
            name="资质有效期",
            score=100,
            status="passed",
            summary="全部资质有效",
            deeplink=f"/dashboard/enterprises/{project.enterprise_id}?tab=credentials",
        )

        if not project.enterprise_id:
            dim.status = "warning"
            dim.summary = "项目未关联企业，无法检查资质"
            dim.score = 50
            dim.issue_count = 1
            return dim

        try:
            from app.services.credential_alert_service import CredentialAlertService
            svc = CredentialAlertService(self.session)
            cred_report = await svc.check_bid_readiness(
                enterprise_id=project.enterprise_id,
                tenant_id=tenant_id,
                bid_open_date=project.deadline[:10] if project.deadline else None,
            )

            if cred_report.expired_count > 0:
                dim.status = "failed"
                dim.score = 0
                dim.summary = f"{cred_report.expired_count} 个资质已过期，投标将被拒绝"
                dim.issue_count = cred_report.expired_count
            elif cred_report.warning_count > 0:
                dim.status = "warning"
                dim.score = max(40, 100 - cred_report.warning_count * 15)
                dim.summary = f"{cred_report.warning_count} 个资质即将过期"
                dim.issue_count = cred_report.warning_count
            else:
                dim.summary = f"{cred_report.total_credentials} 个资质全部有效"

        except Exception as e:
            logger.warning(f"[体检-资质] 调用失败: {e}")
            dim.status = "error"
            dim.summary = "资质检查服务异常"
            dim.score = 50

        return dim

    # ── 维度2: 合规检查（废标/资格/评分） ────────────

    async def _check_compliance(
        self, project_id: int, tenant_id: int
    ) -> CheckupDimension:
        """调用 BidComplianceService.check()"""
        dim = CheckupDimension(
            name="合规检查",
            score=100,
            status="passed",
            summary="合规检查全部通过",
            deeplink=f"/dashboard/bid-projects/{project_id}/compliance",
        )

        try:
            from app.services.bid_compliance_service import BidComplianceService
            svc = BidComplianceService(self.session)
            result = await svc.check(project_id, tenant_id)

            failed = result.get("failed", 0)
            warning = result.get("warning", 0)
            total = result.get("total", 0)

            if failed > 0:
                dim.status = "failed"
                dim.score = max(0, 100 - failed * 20 - warning * 5)
                dim.summary = f"{failed} 项严重不合规（废标风险）"
                dim.issue_count = failed
            elif warning > 0:
                dim.status = "warning"
                dim.score = max(50, 100 - warning * 10)
                dim.summary = f"{warning} 项需人工复核"
                dim.issue_count = warning
            else:
                dim.summary = f"{total} 项要求全部合规"

        except Exception as e:
            logger.warning(f"[体检-合规] 调用失败: {e}")
            dim.status = "error"
            dim.summary = "合规检查服务异常"
            dim.score = 50

        return dim

    # ── 维度3: 风险报告 ──────────────────────────────

    async def _check_risk_report(
        self, project_id: int, tenant_id: int
    ) -> CheckupDimension:
        """调用 RiskReportService.generate_report()"""
        dim = CheckupDimension(
            name="风险报告",
            score=100,
            status="passed",
            summary="无致命风险",
            deeplink=f"/dashboard/bid-projects/{project_id}/risk-report",
        )

        try:
            from app.services.risk_report_service import RiskReportService
            svc = RiskReportService(self.session)
            result = await svc.generate_report(project_id, tenant_id)

            fatal = result.get("fatal_count", 0)
            serious = result.get("serious_count", 0)

            if fatal > 0:
                dim.status = "failed"
                dim.score = 0
                dim.summary = f"{fatal} 个致命风险，导出将被阻断"
                dim.issue_count = fatal
            elif serious > 0:
                dim.status = "warning"
                dim.score = max(40, 100 - serious * 12)
                dim.summary = f"{serious} 个严重风险建议修复"
                dim.issue_count = serious
            else:
                dim.summary = "全部风险项已通过"

        except Exception as e:
            logger.warning(f"[体检-风险] 调用失败: {e}")
            dim.status = "error"
            dim.summary = "风险报告服务异常"
            dim.score = 50

        return dim

    # ── 维度4: 评分覆盖率 ────────────────────────────

    async def _check_scoring_coverage(
        self, project_id: int, tenant_id: int
    ) -> CheckupDimension:
        """调用 ScoringExtractor（W3-D8D10 产物）"""
        dim = CheckupDimension(
            name="评分覆盖",
            score=100,
            status="passed",
            summary="全部评分项已响应",
            deeplink=f"/dashboard/bid-projects/{project_id}/coverage",
        )

        try:
            from app.services.scoring_extractor import ScoringExtractor
            extractor = ScoringExtractor(self.session)
            matrix = await extractor.extract(project_id, tenant_id)

            total = len(matrix.items)
            high_priority = sum(1 for i in matrix.items if i.priority == "high")

            if total == 0:
                dim.status = "warning"
                dim.score = 50
                dim.summary = "未提取到评分矩阵，建议先解析招标文件"
                dim.issue_count = 1
            else:
                dim.summary = (
                    f"评分矩阵 {total} 项（{high_priority} 项高权重），"
                    f"总分 {matrix.total_score}"
                )

        except Exception as e:
            logger.warning(f"[体检-评分] 调用失败: {e}")
            dim.status = "error"
            dim.summary = "评分提取服务异常"
            dim.score = 50

        return dim

    # ── 维度5: 数据一致性 ────────────────────────────

    async def _check_consistency(
        self, project_id: int, tenant_id: int
    ) -> CheckupDimension:
        """调用 compliance_gate 做跨章节一致性检查"""
        dim = CheckupDimension(
            name="数据一致性",
            score=100,
            status="passed",
            summary="跨章节数据一致",
            deeplink=f"/dashboard/bid-projects/{project_id}/chapters",
        )

        try:
            from app.services.bid_project_service import BidProjectService
            svc = BidProjectService(self.session)
            project = await svc.get_project(project_id, tenant_id)
            if not project or not project.chapters:
                dim.status = "warning"
                dim.summary = "无章节可检查"
                dim.score = 50
                return dim

            # 复用 compliance_gate 的一致性检查（需构造 DraftChapter duck-type）
            from app.services.generation.compliance_gate import (
                _check_cross_chapter_consistency,
            )
            from app.services.generation.writer import DraftChapter

            drafts = [
                DraftChapter(
                    chapter_no=ch.chapter_no,
                    title=ch.title,
                    content=ch.content or "",
                )
                for ch in project.chapters
            ]
            issues = _check_cross_chapter_consistency(drafts)

            if issues:
                dim.status = "warning"
                dim.score = max(40, 100 - len(issues) * 15)
                dim.summary = f"{len(issues)} 处数据前后不一致"
                dim.issue_count = len(issues)
            else:
                dim.summary = f"{len(project.chapters)} 个章节数据一致"

        except Exception as e:
            logger.warning(f"[体检-一致性] 调用失败: {e}")
            dim.status = "error"
            dim.summary = "一致性检查服务异常"
            dim.score = 50

        return dim

    # ── Application 层独立查询 ───────────────────────

    async def _load_project(
        self, project_id: int, tenant_id: int
    ) -> Optional[BidProject]:
        """加载项目（tenant_id 强制隔离）"""
        result = await self.session.execute(
            select(BidProject).where(
                BidProject.id == project_id,
                BidProject.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()
