"""
风险报告服务 — 聚合多维度检查，输出三级告警

三级告警:
  - FATAL (致命): 废标项未满足、必需资质缺失 → 投标直接无效
  - SERIOUS (严重): 评分覆盖率低、章节未响应关键要求 → 大幅丢分
  - ADVICE (建议): 内容可优化、格式规范、竞争力提升 → 锦上添花

数据源:
  1. TenderRequirement.compliance_status (来自 bid_compliance_service)
  2. Enterprise + Credential (资质完整度)
  3. BidChapter (内容覆盖率)
  4. QuotationSheet (报价合理性)
"""
from typing import Optional
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bid_project import BidProject, TenderRequirement, BidChapter
from app.models.enterprise import Enterprise
from app.models.credential import Credential
from app.models.quotation import QuotationSheet
from app.services.bid_project_service import BidProjectService
from app.core.config import settings


class RiskItem:
    """单条风险项"""
    def __init__(self, level: str, category: str, title: str, detail: str, suggestion: str = ""):
        self.level = level  # fatal / serious / advice
        self.category = category
        self.title = title
        self.detail = detail
        self.suggestion = suggestion

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "suggestion": self.suggestion,
        }


class RiskReportService:
    """风险报告服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_report(self, project_id: int, tenant_id: int) -> dict:
        """生成完整风险报告"""
        svc = BidProjectService(self.session)
        project = await svc.get_project(project_id, tenant_id)
        if not project:
            raise ValueError("投标项目不存在")

        risks: list[RiskItem] = []

        # 1. 合规检查风险
        risks.extend(self._check_compliance_risks(project))

        # 2. 资质完整度
        enterprise = None
        credentials = []
        if project.enterprise_id:
            ent_result = await self.session.execute(
                select(Enterprise).where(
                    Enterprise.id == project.enterprise_id,
                    Enterprise.tenant_id == tenant_id,
                )
            )
            enterprise = ent_result.scalar_one_or_none()
            if enterprise:
                cred_result = await self.session.execute(
                    select(Credential).where(
                        Credential.enterprise_id == enterprise.id,
                        Credential.tenant_id == tenant_id,
                    )
                )
                credentials = list(cred_result.scalars().all())

        risks.extend(self._check_enterprise_risks(project, enterprise, credentials))

        # 3. 章节内容风险
        risks.extend(self._check_chapter_risks(project))

        # 4. 报价风险
        quotation = await self._load_latest_quotation(project_id, tenant_id)
        risks.extend(self._check_quotation_risks(project, quotation))

        # 汇总
        fatal_count = sum(1 for r in risks if r.level == "fatal")
        serious_count = sum(1 for r in risks if r.level == "serious")
        advice_count = sum(1 for r in risks if r.level == "advice")

        return {
            "project_id": project_id,
            "project_name": project.project_name,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": len(risks),
                "fatal": fatal_count,
                "serious": serious_count,
                "advice": advice_count,
                "can_submit": fatal_count == 0,
            },
            "risks": [r.to_dict() for r in risks],
        }

    def _check_compliance_risks(self, project: BidProject) -> list[RiskItem]:
        """从已有合规检查结果提取风险"""
        risks = []
        for req in project.requirements:
            if req.compliance_status == "failed":
                level = "fatal" if req.category == "disqualification" else "serious"
                risks.append(RiskItem(
                    level=level,
                    category="合规检查",
                    title=f"{'废标风险' if req.category == 'disqualification' else '要求未满足'}: {req.content[:50]}",
                    detail=req.compliance_note or req.content,
                    suggestion="请立即补充相关资质或在章节中补充响应内容",
                ))
            elif req.compliance_status == "warning":
                risks.append(RiskItem(
                    level="serious" if req.category in ("disqualification", "scoring") else "advice",
                    category="合规检查",
                    title=f"待确认: {req.content[:50]}",
                    detail=req.compliance_note or "关键词匹配不充分，建议人工复核",
                    suggestion="建议在相关章节补充明确响应",
                ))
        return risks

    def _check_enterprise_risks(
        self, project: BidProject, enterprise: Optional[Enterprise], credentials: list[Credential]
    ) -> list[RiskItem]:
        """企业信息完整度检查"""
        risks = []

        if not enterprise:
            risks.append(RiskItem(
                level="fatal", category="企业信息",
                title="未关联投标企业",
                detail="项目未关联任何企业信息，导出的投标文件将缺少企业信息",
                suggestion="请在项目详情页关联或新建企业",
            ))
            return risks

        # 关键字段缺失
        if not enterprise.credit_code:
            risks.append(RiskItem(
                level="serious", category="企业信息",
                title="统一社会信用代码未填写",
                detail="投标文件封面和资格审查需要此信息",
                suggestion="请在企业信息页补充",
            ))
        if not enterprise.legal_representative:
            risks.append(RiskItem(
                level="serious", category="企业信息",
                title="法定代表人未填写",
                detail="投标函和授权书需要此信息",
                suggestion="请在企业信息页补充",
            ))
        if not enterprise.food_license_no:
            risks.append(RiskItem(
                level="fatal", category="企业信息",
                title="食品经营许可证号未填写",
                detail="食材配送招标通常要求提供食品经营许可证，缺失可能导致废标",
                suggestion="请在企业信息页补充许可证号",
            ))

        # 资质到期检查
        for cred in credentials:
            if cred.expiry_date and not cred.is_permanent:
                try:
                    expiry = datetime.strptime(cred.expiry_date, "%Y-%m-%d")
                    days_left = (expiry - datetime.now()).days
                    if days_left < 0:
                        risks.append(RiskItem(
                            level="fatal", category="资质证书",
                            title=f"证书已过期: {cred.cred_name}",
                            detail=f"过期日期: {cred.expiry_date}，已过期 {abs(days_left)} 天",
                            suggestion="请更新证书或联系发证机关续期",
                        ))
                    elif days_left < settings.CREDENTIAL_EXPIRY_WARN_DAYS:
                        risks.append(RiskItem(
                            level="advice", category="资质证书",
                            title=f"证书即将到期: {cred.cred_name}",
                            detail=f"将于 {cred.expiry_date} 到期（剩余 {days_left} 天）",
                            suggestion="建议提前续期，避免投标期间证书失效",
                        ))
                except ValueError:
                    pass

        return risks

    def _check_chapter_risks(self, project: BidProject) -> list[RiskItem]:
        """章节内容风险检查"""
        risks = []

        if not project.chapters:
            risks.append(RiskItem(
                level="fatal", category="章节内容",
                title="投标章节未初始化",
                detail="项目尚未生成任何章节内容",
                suggestion="请先初始化章节结构并生成内容",
            ))
            return risks

        empty_chapters = [ch for ch in project.chapters if not ch.content or len(ch.content.strip()) < 50]
        ai_chapters = [ch for ch in project.chapters if ch.source == "ai"]

        if empty_chapters:
            names = ", ".join(f"{ch.chapter_no}" for ch in empty_chapters[:3])
            risks.append(RiskItem(
                level="serious", category="章节内容",
                title=f"{len(empty_chapters)} 个章节内容不足",
                detail=f"以下章节内容为空或过短: {names}{'...' if len(empty_chapters) > 3 else ''}",
                suggestion="请为这些章节生成或手动编写内容",
            ))

        # 未生成的 AI 章节
        ungenerated = [ch for ch in ai_chapters if ch.status == "draft"]
        if ungenerated:
            risks.append(RiskItem(
                level="serious", category="章节内容",
                title=f"{len(ungenerated)} 个 AI 章节尚未生成",
                detail=f"需要 AI 生成的章节仍为草稿状态",
                suggestion="请点击「一键生成全部」",
            ))

        return risks

    def _check_quotation_risks(
        self, project: BidProject, quotation: Optional[QuotationSheet]
    ) -> list[RiskItem]:
        """报价风险检查"""
        risks = []

        if not quotation:
            risks.append(RiskItem(
                level="serious", category="报价",
                title="未创建报价单",
                detail="投标文件第八章（报价文件）将无报价数据",
                suggestion="请在报价管理页面初始化报价单",
            ))
            return risks

        if not quotation.total_amount or quotation.total_amount == 0:
            risks.append(RiskItem(
                level="serious", category="报价",
                title="报价总额为零",
                detail="报价明细未填写数量，无法计算总额",
                suggestion="请填写报价明细的数量并重算总额",
            ))

        if project.budget_amount and quotation.total_amount:
            if quotation.total_amount > project.budget_amount:
                risks.append(RiskItem(
                    level="fatal", category="报价",
                    title="报价超预算",
                    detail=f"报价 ¥{quotation.total_amount:,.2f} 超过预算 ¥{project.budget_amount:,.2f}",
                    suggestion="请降低报价或调整下浮率",
                ))

        return risks

    async def _load_latest_quotation(self, project_id: int, tenant_id: int) -> Optional[QuotationSheet]:
        result = await self.session.execute(
            select(QuotationSheet)
            .where(QuotationSheet.project_id == project_id)
            .where(QuotationSheet.tenant_id == tenant_id)
            .order_by(QuotationSheet.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
