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

        # 4. 评分覆盖检查
        risks.extend(self._check_scoring_coverage(project))

        # 5. 报价风险
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

        # 资质到期检查（含投标截止日比对）
        project_deadline = None
        if project.deadline:
            try:
                project_deadline = datetime.strptime(project.deadline[:10], "%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        for cred in credentials:
            if cred.expiry_date and not cred.is_permanent:
                try:
                    expiry = datetime.strptime(cred.expiry_date, "%Y-%m-%d")
                    now = datetime.now()
                    days_left = (expiry - now).days

                    if days_left < 0:
                        # 已过期 → Fatal
                        risks.append(RiskItem(
                            level="fatal", category="资质证书",
                            title=f"证书已过期: {cred.cred_name}",
                            detail=f"过期日期: {cred.expiry_date}，已过期 {abs(days_left)} 天",
                            suggestion="请更新证书或联系发证机关续期",
                        ))
                    elif project_deadline and expiry < project_deadline:
                        # 今天还有效但投标截止日前会过期 → Fatal
                        days_to_expire = (expiry - now).days
                        days_to_deadline = (project_deadline - now).days
                        risks.append(RiskItem(
                            level="fatal", category="资质证书",
                            title=f"证书将在投标截止日前过期: {cred.cred_name}",
                            detail=f"证书到期日 {cred.expiry_date}（剩余 {days_to_expire} 天），"
                                   f"投标截止日 {project.deadline[:10]}（剩余 {days_to_deadline} 天）。"
                                   f"评标时该资质已失效，将被判定资格不合格。",
                            suggestion="请立即联系发证机关办理续期，确保证书在投标截止日后仍有效",
                        ))
                    elif days_left < settings.CREDENTIAL_EXPIRY_WARN_DAYS:
                        # 即将到期（但不影响本次投标）→ Advice
                        risks.append(RiskItem(
                            level="advice", category="资质证书",
                            title=f"证书即将到期: {cred.cred_name}",
                            detail=f"将于 {cred.expiry_date} 到期（剩余 {days_left} 天）",
                            suggestion="建议提前续期，避免后续投标时证书失效",
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

    def _check_scoring_coverage(self, project: BidProject) -> list[RiskItem]:
        """评分覆盖逐条检查 — 评分矩阵子项 vs 章节内容关键词匹配"""
        import re

        risks = []

        # 提取评分类需求
        scoring_reqs = [r for r in project.requirements if r.category == "scoring"]
        if not scoring_reqs or not project.chapters:
            return risks

        # 合并所有章节内容为全文（用于关键词搜索）
        all_content = "\n".join(ch.content or "" for ch in project.chapters)
        if not all_content.strip():
            return risks

        for req in scoring_reqs:
            content_text = req.content or ""
            if not content_text.strip():
                continue

            # 从评分项描述中提取关键词（取前 3-5 个有意义的词）
            # 去除常见停用词和标点
            clean = re.sub(r'[，。、；：""''（）\(\)\[\]【】\d\s]+', ' ', content_text)
            words = [w for w in clean.split() if len(w) >= 2]
            keywords = words[:5] if words else [content_text[:10]]

            # 在全文中匹配关键词（至少匹配到 1 个算覆盖）
            matched = any(kw in all_content for kw in keywords)

            if not matched:
                # 判定严重程度
                max_score = req.max_score or 0
                is_mandatory = req.is_mandatory

                if is_mandatory:
                    level = "fatal"
                    title_prefix = "废标级评分项未响应"
                elif max_score >= 10:
                    level = "serious"
                    title_prefix = "高分评分项未响应"
                elif max_score >= 5:
                    level = "serious"
                    title_prefix = "评分项未响应"
                else:
                    level = "advice"
                    title_prefix = "低分评分项未响应"

                score_info = f"（{max_score}分）" if max_score else ""
                risks.append(RiskItem(
                    level=level,
                    category="评分覆盖",
                    title=f"{title_prefix}: {content_text[:40]}{score_info}",
                    detail=f"评分项: {content_text}\n关键词: {', '.join(keywords)}\n在投标章节中未找到对应响应内容",
                    suggestion="请在相关章节中补充对该评分项的明确响应",
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
