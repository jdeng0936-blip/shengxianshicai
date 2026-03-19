"""
文档生成引擎 — 编排全链路：参数→规则匹配→计算→模板填充→Word 输出

流程：
  1. 加载 ProjectParams + Project 基础信息
  2. 调用 RuleService.match_rules() → 命中规则+章节列表
  3. 调用 SupportCalcEngine + VentCalcEngine → 计算结果
  4. 按章节顺序组装内容
  5. python-docx 生成 .docx 文件
"""
import os
from datetime import datetime
from typing import Optional

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectParams
from app.schemas.calc import SupportCalcInput
from app.schemas.vent import VentCalcInput
from app.schemas.doc import ChapterContent, DocGenerateResult
from app.services.calc_engine import SupportCalcEngine
from app.services.vent_engine import VentCalcEngine
from app.services.rule_service import RuleService


# 参数字段中文映射
PARAM_LABELS: dict[str, str] = {
    "rock_class": "围岩级别", "coal_thickness": "煤层厚度(m)",
    "coal_dip_angle": "煤层倾角(°)", "gas_level": "瓦斯等级",
    "hydro_type": "水文地质类型", "geo_structure": "地质构造",
    "spontaneous_combustion": "自燃倾向性", "roadway_type": "巷道类型",
    "excavation_type": "掘进类型", "section_form": "断面形式",
    "section_width": "断面宽度(m)", "section_height": "断面高度(m)",
    "excavation_length": "掘进长度(m)", "service_years": "服务年限(年)",
    "dig_method": "掘进方式", "dig_equipment": "掘进设备",
    "transport_method": "运输方式",
}


class DocGenerator:
    """文档生成引擎"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate(
        self, project_id: int, tenant_id: int, include_calc: bool = True
    ) -> DocGenerateResult:
        """
        端到端文档生成

        Returns:
            DocGenerateResult 包含文件路径和章节列表
        """
        # 1. 加载项目信息
        project = await self._load_project(project_id, tenant_id)
        if not project:
            raise ValueError("项目不存在或无权访问")

        params = await self._load_params(project_id)
        params_dict = self._params_to_dict(params) if params else {}

        # 2. 规则匹配
        rule_svc = RuleService(self.session)
        match_result = None
        try:
            match_result = await rule_svc.match_rules(project_id, tenant_id)
        except ValueError:
            pass  # 参数未填写时跳过匹配

        # 3. 计算引擎
        calc_result = None
        vent_result = None
        if include_calc and params:
            calc_result = self._run_support_calc(params_dict)
            vent_result = self._run_vent_calc(params_dict)

        # 4. 组装章节
        chapters = self._assemble_chapters(
            project, params_dict, match_result, calc_result, vent_result
        )

        # 4.5 智能深度润色（AI赋能）
        chapters = await self._ai_polish_content(chapters, params_dict)

        # 5. 生成 Word
        file_path = self._render_docx(project, chapters, calc_result, vent_result)

        total_warnings = 0
        if calc_result:
            total_warnings += len(calc_result.warnings)
        if vent_result:
            total_warnings += len(vent_result.warnings)

        return DocGenerateResult(
            project_id=project_id,
            project_name=project.face_name,
            file_path=file_path,
            total_chapters=len(chapters),
            total_warnings=total_warnings,
            chapters=chapters,
        )

    # ========== 加载数据 ==========

    async def _load_project(self, pid: int, tid: int) -> Optional[Project]:
        result = await self.session.execute(
            select(Project).where(Project.id == pid, Project.tenant_id == tid)
        )
        return result.scalar_one_or_none()

    async def _load_params(self, pid: int) -> Optional[ProjectParams]:
        result = await self.session.execute(
            select(ProjectParams).where(ProjectParams.project_id == pid)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _params_to_dict(params: ProjectParams) -> dict:
        return {
            c.key: getattr(params, c.key)
            for c in params.__table__.columns
            if c.key not in ("id", "project_id")
        }

    # ========== 计算引擎调用 ==========

    @staticmethod
    def _run_support_calc(p: dict):
        try:
            inp = SupportCalcInput(
                rock_class=p.get("rock_class", "III"),
                section_form=p.get("section_form", "矩形"),
                section_width=float(p.get("section_width", 4.5)),
                section_height=float(p.get("section_height", 3.2)),
            )
            return SupportCalcEngine.calculate(inp)
        except Exception:
            return None

    @staticmethod
    def _run_vent_calc(p: dict):
        try:
            inp = VentCalcInput(
                gas_emission=float(p.get("gas_emission", 2.0) or 2.0),
                gas_level=p.get("gas_level", "低瓦斯"),
                section_area=float(p.get("section_width", 4.5)) * float(p.get("section_height", 3.2)),
                excavation_length=float(p.get("excavation_length", 300)),
            )
            return VentCalcEngine.calculate(inp)
        except Exception:
            return None

    # ========== 章节组装 ==========

    def _assemble_chapters(self, project, params_dict, match_result, calc_result, vent_result):
        chapters: list[ChapterContent] = []

        # 第一章 概况
        overview_lines = [
            f"项目名称：{project.face_name}",
            f"矿井名称：{getattr(project, 'mine_name', '—')}",
        ]
        for field, label in PARAM_LABELS.items():
            val = params_dict.get(field, "—")
            if val is not None:
                overview_lines.append(f"{label}：{val}")

        chapters.append(ChapterContent(
            chapter_no="第一章", title="工程概况",
            content="\n".join(overview_lines), source="template",
        ))

        # 第二章 支护设计（来自计算引擎）
        if calc_result:
            support_lines = [
                f"断面净面积：{calc_result.section_area} m²",
                f"单根锚杆锚固力：{calc_result.bolt_force} kN",
                f"最大允许锚杆间距：{calc_result.max_bolt_spacing} mm",
                f"最大允许排距：{calc_result.max_bolt_row_spacing} mm",
                f"推荐每排锚杆数：{calc_result.recommended_bolt_count_per_row} 根",
                f"最少锚索数量：{calc_result.min_cable_count} 根",
                f"支护密度：{calc_result.support_density} 根/m²",
                f"安全系数：{calc_result.safety_factor}",
            ]
            if calc_result.warnings:
                support_lines.append("")
                support_lines.append("【合规预警】")
                for w in calc_result.warnings:
                    support_lines.append(f"  ⚠ {w.message}")

            chapters.append(ChapterContent(
                chapter_no="第二章", title="支护设计",
                content="\n".join(support_lines), source="calc_engine",
                has_warning=not calc_result.is_compliant,
            ))

        # 第三章 通风系统（来自计算引擎）
        if vent_result:
            vent_lines = [
                f"瓦斯涌出法需风量：{vent_result.q_gas} m³/min",
                f"人数法需风量：{vent_result.q_people} m³/min",
                f"炸药法需风量：{vent_result.q_explosive} m³/min",
                f"最终配风量：{vent_result.q_required} m³/min",
                f"推荐局扇：{vent_result.recommended_fan}（{vent_result.fan_power} kW）",
            ]
            if vent_result.warnings:
                vent_lines.append("")
                vent_lines.append("【合规预警】")
                for w in vent_result.warnings:
                    vent_lines.append(f"  ⚠ {w.message}")

            chapters.append(ChapterContent(
                chapter_no="第三章", title="通风系统",
                content="\n".join(vent_lines), source="calc_engine",
                has_warning=not vent_result.is_compliant,
            ))

        # 第四章+ 规则匹配命中的章节
        if match_result and match_result.matched_rules:
            rule_lines = []
            for mr in match_result.matched_rules:
                rule_lines.append(f"• {mr.rule_name}（{mr.category}，优先级 {mr.priority}）")
                for a in mr.actions:
                    rule_lines.append(f"  → 关联章节：{a.target_chapter}")

            chapters.append(ChapterContent(
                chapter_no="第四章", title="编制依据与规则命中",
                content="\n".join(rule_lines), source="rule_match",
            ))

        # 第五章 安全技术措施（模板）
        chapters.append(ChapterContent(
            chapter_no="第五章", title="安全技术措施",
            content=(
                "一、顶板管理\n"
                "  掘进工作面应当严格执行敲帮问顶制度...\n\n"
                "二、防治水措施\n"
                '  坚持"有疑必探、先探后掘"的原则...\n\n'
                "三、瓦斯管理\n"
                "  严格执行瓦斯检查制度，瓦斯超限必须停止作业...\n\n"
                "四、防尘措施\n"
                "  采用湿式打眼、喷雾降尘、通风除尘等综合防尘措施..."
            ),
            source="template",
        ))

        return chapters

    async def _ai_polish_content(self, chapters: list[ChapterContent], params: dict) -> list[ChapterContent]:
        """
        AI 深度润色长尾章节 — RAG 增强版

        流程:
          1. 对每个须润色的章节，用章节标题检索标准库 + 知识库
          2. 将检索到的规程片段注入 LLM System Prompt
          3. LLM 基于客户真实规程生成更贴合实际的内容
        """
        from app.core.config import settings
        from openai import AsyncOpenAI
        from app.services.embedding_service import EmbeddingService

        api_key = settings.OPENAI_API_KEY or settings.GEMINI_API_KEY
        base_url = settings.OPENAI_BASE_URL or None
        model = settings.AI_MODEL

        if not api_key:
            return chapters  # 降级：无大模型配置时原样返回

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = AsyncOpenAI(**client_kwargs)

        # RAG 检索服务
        emb_svc = EmbeddingService(self.session)

        for ch in chapters:
            if "安全技术措施" in ch.title or "灾害预防" in ch.title or "支护" in ch.title:
                # ===== RAG 检索：标准库 + 知识库 =====
                rag_context_parts = []

                # L1a: 标准库条款
                std_results = await emb_svc.search_similar(
                    query=ch.title, tenant_id=1, top_k=3, threshold=0.4
                )
                if std_results:
                    rag_context_parts.append("【标准库参考条款】")
                    for r in std_results:
                        rag_context_parts.append(
                            f"- [{r['doc_title']}] {r['clause_no']}: {r['content'][:300]}"
                        )

                # L1b: 知识库（客户规程片段）
                snippet_results = await emb_svc.search_snippets(
                    query=ch.title, tenant_id=1, top_k=5, threshold=0.4
                )
                if snippet_results:
                    rag_context_parts.append("\n【客户规程参考内容】")
                    for r in snippet_results:
                        rag_context_parts.append(
                            f"- [{r['chapter_name']}]: {r['content'][:300]}"
                        )

                rag_context = "\n".join(rag_context_parts)
                rag_note = ""
                if rag_context:
                    rag_note = (
                        f"\n\n以下是从客户已有规程和国家标准中检索到的相关内容，"
                        f"请务必参考并融入你的输出中，确保与客户实际情况一致：\n{rag_context}\n"
                    )

                prompt = (
                    f"请作为顶尖煤矿安全专家，根据以下参数对作业规程的【{ch.title}】章节进行扩充、润色，"
                    f"使其更符合现场实际，具备可操作性，避免生硬的模板拼接感。\n"
                    f"地质条件与参数: {params}\n"
                    f"原始内容框架:\n{ch.content}"
                    f"{rag_note}\n\n"
                    "要求：\n"
                    "1. 直接输出润色后的篇章正式内容，不要包含任何前言后语和分析推理过程。\n"
                    "2. 分条列出，层级清晰，重点突出。\n"
                    "3. 如引用了参考资料中的具体数值标准，请在文中自然融入。"
                )
                try:
                    resp = await client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    polished = resp.choices[0].message.content
                    if polished:
                        ch.content = polished
                        ch.source = "ai_polished"
                except Exception as e:
                    print(f"⚠️ AI 润色失败: {e}")

        return chapters

    # ========== Word 渲染 ==========

    def _render_docx(self, project, chapters, calc_result, vent_result) -> str:
        """用 python-docx 生成 .docx 文件"""
        doc = Document()

        # 文档样式
        style = doc.styles["Normal"]
        style.font.name = "宋体"
        style.font.size = Pt(12)

        # --- 封面 ---
        for _ in range(4):
            doc.add_paragraph()

        title = doc.add_paragraph()
        title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        run = title.add_run(f"{project.face_name}")
        run.font.size = Pt(22)
        run.font.bold = True

        subtitle = doc.add_paragraph()
        subtitle.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        run2 = subtitle.add_run("掘进工作面作业规程")
        run2.font.size = Pt(18)

        doc.add_paragraph()

        meta_items = [
            f"矿井名称：{getattr(project, 'mine_name', '—')}",
            f"编制日期：{datetime.now().strftime('%Y年%m月%d日')}",
            f"编制单位：生产技术科",
        ]
        for item in meta_items:
            p = doc.add_paragraph()
            p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            p.add_run(item).font.size = Pt(14)

        doc.add_page_break()

        # --- 正文章节 ---
        for ch in chapters:
            # 章节标题
            heading = doc.add_heading(f"{ch.chapter_no}  {ch.title}", level=1)

            # 预警标记
            if ch.has_warning:
                warn_p = doc.add_paragraph()
                warn_run = warn_p.add_run("⚠ 本章节存在合规预警，请重点审查")
                warn_run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
                warn_run.font.bold = True

            # 章节内容
            for line in ch.content.split("\n"):
                if line.startswith("  ⚠"):
                    p = doc.add_paragraph()
                    run = p.add_run(line)
                    run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
                elif line.startswith("【"):
                    p = doc.add_paragraph()
                    run = p.add_run(line)
                    run.font.bold = True
                else:
                    doc.add_paragraph(line)

        # --- 保存 ---
        output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "storage", "outputs"
        )
        os.makedirs(output_dir, exist_ok=True)

        safe_name = project.face_name.replace("/", "_").replace(" ", "_")
        filename = f"{safe_name}_作业规程_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        file_path = os.path.join(output_dir, filename)

        doc.save(file_path)
        return file_path
