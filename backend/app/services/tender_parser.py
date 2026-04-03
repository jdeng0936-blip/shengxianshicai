"""
招标文件解析服务 — 上传 → 文本提取 → LLM 结构化解析

支持格式: .pdf (pymupdf/pdfplumber) / .docx (python-docx) / .doc (textutil)
解析流程: 文件 → 纯文本 → 分块 → LLM 结构化 JSON → TenderRequirement 入库
"""
import json
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
import yaml
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.prompt_manager import prompt_manager
from app.core.llm_selector import LLMSelector
from app.models.bid_project import BidProject, BidProjectStatus
from app.schemas.bid_project import TenderRequirementCreate
from app.services.bid_project_service import BidProjectService
from app.services.document_parser import extract_text

# 招标文件存储根目录
TENDER_UPLOAD_ROOT = Path("storage/tenders")

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}

# 每块最大字符数（配合 LLM max_tokens 限制）
CHUNK_MAX_CHARS = 8000




def extract_text_from_pdf(file_path: str) -> str:
    """从 PDF 文件提取纯文本"""
    try:
        import fitz  # pymupdf
        doc = fitz.open(file_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    except ImportError:
        # fallback 到 pdfplumber
        import pdfplumber
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n".join(text_parts)


def extract_tender_text(file_path: str, filename: str) -> str:
    """根据文件扩展名选择提取方式"""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in (".docx", ".doc", ".txt"):
        return extract_text(file_path, filename)
    else:
        raise ValueError(f"不支持的文件格式: {ext}，仅支持 .pdf/.docx/.doc")


def _clean_text(text: str) -> str:
    """清洗文本：去除页眉页脚/页码/多余空行"""
    # 去除常见页眉页脚格式
    text = re.sub(r'第\s*\d+\s*页\s*(共\s*\d+\s*页)?', '', text)
    text = re.sub(r'- \d+ -', '', text)
    # 合并多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 去除 NUL 和控制字符
    text = text.replace('\x00', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text.strip()


# ══════════════════════════════════════════════════════════════
# 废标条款关键词库 + 规则引擎（P0 安全红线：关键词硬检查兜底 LLM）
# ══════════════════════════════════════════════════════════════

DISQUALIFICATION_KEYWORDS = [
    # —— 明确废标/否决表述 ——
    "将被否决", "取消投标资格", "不予评审", "视为无效投标",
    "按废标处理", "投标无效", "否决其投标", "不得进入评审",
    "不予受理", "拒绝投标", "取消中标资格", "失去中标资格",
    "不合格投标", "无效标", "废标", "不予通过",
    "不符合资格", "丧失投标资格", "自动放弃", "视为放弃",
    "拒绝其投标", "不接受投标", "不得参与", "不予中标",
    "予以否决", "作废标处理", "按无效标处理", "按废标论处",
    # —— 资格/证照缺失 ——
    "未提供有效", "未取得", "未办理", "未具备",
    "不具备相应资质", "缺少必要证照", "证书过期", "许可证失效",
    "未在有效期内", "未年检", "营业执照过期",
    "食品经营许可证过期", "无食品经营许可", "无营业执照",
    # —— 投标文件形式缺陷 ——
    "未按规定密封", "未按要求装订", "投标文件份数不足",
    "未提交投标保证金", "保证金不足", "保证金未到账",
    "未加盖公章", "未签字盖章", "缺少法定代表人签字",
    "授权书无效", "授权委托书缺失", "委托书未公证",
    "未提交原件", "复印件未盖章", "扫描件不清晰",
    # —— 响应性/实质偏离 ——
    "实质性偏离", "重大偏离", "不满足星号条款",
    "未响应带星号要求", "未满足强制要求", "不符合实质性要求",
    "偏离招标文件要求", "未按招标文件要求", "响应不完整",
    # —— 价格/报价问题 ——
    "报价超过预算", "报价超过最高限价", "低于成本报价",
    "报价缺少单价明细", "未按格式填写报价", "报价表空白",
    "总价与单价不一致", "报价涂改", "大小写金额不一致",
    # —— 诚信/违法 ——
    "串通投标", "围标", "挂靠", "借用资质",
    "提供虚假材料", "弄虚作假", "行贿记录",
    "被列入黑名单", "信用惩戒", "失信被执行人",
    "重大违法记录", "行政处罚", "刑事处罚",
    # —— 时间/程序问题 ——
    "逾期送达", "超过截止时间", "未按时送达",
    "未参加开标", "未到场", "缺席开标会议",
    # —— 利益冲突 ——
    "存在利害关系", "与采购人有利害关系", "关联交易",
    "法定代表人为同一人", "存在控股关系", "存在管理关系",
    # —— 生鲜配送专项 ——
    "无冷链运输车辆", "无冷库", "无冷藏设施",
    "食品安全事故", "食物中毒", "无HACCP", "无ISO22000",
    "无SC认证", "无食品生产许可", "配送能力不足",
    "无健康证", "从业人员无健康证明",
]

# 否定条件句式正则（识别"如果X则Y"型废标条件）
_NEGATION_PATTERNS = [
    re.compile(r"(?:如果|若|如|倘若).{2,40}(?:则|将|应|须|必须).{2,60}(?:废标|否决|无效|不予|取消|拒绝)", re.DOTALL),
    re.compile(r"(?:未|不|没有|缺少|缺失).{1,30}(?:将|则|视为|按|作为).{2,40}(?:废标|否决|无效|不予|取消)", re.DOTALL),
    re.compile(r"(?:不得|禁止|严禁).{2,40}(?:否则|违反者|违者).{2,40}(?:废标|否决|无效|取消)", re.DOTALL),
    re.compile(r"(?:必须|应当|须).{2,40}(?:否则|不满足|未满足).{2,40}(?:废标|否决|无效|不予)", re.DOTALL),
]


def _extract_disqualification_items(full_text: str) -> list[dict]:
    """从全文中基于关键词 + 否定条件句式提取废标条款

    双重机制：
      1. 关键词库扫描：在全文中搜索关键词，提取包含关键词的完整句子
      2. 否定条件句式识别：正则匹配"如果...则..."、"未...将..."等模式
      3. 两者取并集后去重

    Returns:
        [{"content": "废标条件描述", "source": "keyword|pattern"}]
    """
    results: list[dict] = []
    seen_sentences: set[str] = set()

    # 按句子分割（句号、分号、换行）
    sentences = re.split(r'[。；\n]+', full_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= 8]

    # 1. 关键词扫描
    for sentence in sentences:
        for keyword in DISQUALIFICATION_KEYWORDS:
            if keyword in sentence:
                # 截断过长句子
                content = sentence[:200] if len(sentence) > 200 else sentence
                if content not in seen_sentences:
                    seen_sentences.add(content)
                    results.append({"content": content, "source": "keyword"})
                break  # 每句匹配一次即可

    # 2. 否定条件句式匹配
    for pattern in _NEGATION_PATTERNS:
        for match in pattern.finditer(full_text):
            content = match.group(0).strip()
            content = content[:200] if len(content) > 200 else content
            if content not in seen_sentences:
                seen_sentences.add(content)
                results.append({"content": content, "source": "pattern"})

    return results


def _chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """将长文本按段落边界分块"""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split('\n\n')
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text[:max_chars]]


def _extract_json_from_response(response_text: str) -> dict:
    """从 LLM 响应中提取 JSON（处理 markdown code block 包裹）"""
    # 尝试提取 ```json ... ``` 块
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_str = response_text.strip()

    return json.loads(json_str)


class TenderParseService:
    """招标文件解析服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    async def save_temp_file(file: UploadFile) -> tuple[str, str]:
        """保存上传文件到临时目录，返回 (临时文件路径, 原始文件名)"""
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}，仅支持 PDF/DOCX/DOC")

        temp_dir = TENDER_UPLOAD_ROOT / "_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        save_name = f"{uuid.uuid4().hex}{ext}"
        save_path = temp_dir / save_name

        content = await file.read()
        async with aiofiles.open(save_path, "wb") as f:
            await f.write(content)

        return str(save_path), file.filename

    @staticmethod
    async def preview_parse(file_path: str, filename: str) -> dict:
        """
        仅提取招标文件基本信息用于预填表单，不写入数据库。
        返回: project_name, buyer_name, customer_type, tender_type,
              budget_amount, deadline, delivery_scope, delivery_period
        """
        from openai import AsyncOpenAI
        import asyncio

        # 提取文本 — 通过线程池执行同步 PDF/DOCX 解析，避免阻塞事件循环
        raw_text = await asyncio.to_thread(extract_tender_text, file_path, filename)
        if not raw_text or len(raw_text.strip()) < 50:
            raise ValueError("招标文件内容为空或过短，无法解析")
        text = _clean_text(raw_text)

        # 只取前 8000 字符做快速预览解析
        preview_text = text[:CHUNK_MAX_CHARS]

        cfg = LLMSelector.get_client_config("tender_parse")
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )

        prompt = (
            "你是专业的招标文件分析师，请快速阅读以下招标文件内容，"
            "仅提取项目基本信息。\n\n"
            "== 招标文件原文 ==\n"
            f"{preview_text}\n\n"
            "请严格按照以下 JSON 格式输出，未找到的字段填 null：\n"
            "{\n"
            '  "project_name": "项目名称",\n'
            '  "buyer_name": "采购方/招标方名称",\n'
            '  "customer_type": "school/hospital/government/enterprise/canteen 之一",\n'
            '  "tender_type": "open/invite/negotiate/inquiry/single 之一",\n'
            '  "budget_amount": 数字（元，不含万字）,\n'
            '  "deadline": "YYYY-MM-DDTHH:MM 格式",\n'
            '  "delivery_scope": "配送范围描述",\n'
            '  "delivery_period": "配送周期/合同期限"\n'
            "}\n\n"
            "注意：只输出 JSON，不要加任何解释。"
        )

        response = await client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=LLMSelector.get_temperature("tender_parse"),
            max_tokens=1024,
        )

        resp_text = response.choices[0].message.content or ""
        try:
            result = _extract_json_from_response(resp_text)
        except (json.JSONDecodeError, ValueError):
            result = {}

        return {
            "project_name": result.get("project_name"),
            "buyer_name": result.get("buyer_name"),
            "customer_type": result.get("customer_type"),
            "tender_type": result.get("tender_type"),
            "budget_amount": result.get("budget_amount"),
            "deadline": result.get("deadline"),
            "delivery_scope": result.get("delivery_scope"),
            "delivery_period": result.get("delivery_period"),
        }

    async def save_tender_file(
        self, project_id: int, tenant_id: int, file: UploadFile
    ) -> tuple[str, str]:
        """保存上传的招标文件，返回 (文件路径, 原始文件名)"""
        # 校验扩展名
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}，仅支持 PDF/DOCX/DOC")

        # 构建存储路径（租户隔离）
        save_dir = TENDER_UPLOAD_ROOT / str(tenant_id) / str(project_id)
        save_dir.mkdir(parents=True, exist_ok=True)
        save_name = f"{uuid.uuid4().hex}{ext}"
        save_path = save_dir / save_name

        # 异步写入文件
        content = await file.read()
        async with aiofiles.open(save_path, "wb") as f:
            await f.write(content)

        return str(save_path), file.filename

    async def extract_text(self, file_path: str, filename: str) -> str:
        """提取并清洗文本"""
        import asyncio
        raw_text = await asyncio.to_thread(extract_tender_text, file_path, filename)
        if not raw_text or len(raw_text.strip()) < 50:
            raise ValueError("招标文件内容为空或过短，无法解析")
        return _clean_text(raw_text)

    async def parse_with_llm(
        self, project_id: int, tenant_id: int, text: str, user_id: int
    ) -> dict:
        """
        使用 LLM 解析招标文件文本，返回结构化结果。

        流程:
        1. 文本分块
        2. 每块调用 LLM tender_parse prompt
        3. 合并多块结果
        4. 写入 TenderRequirement + 更新 BidProject 字段
        """
        from openai import AsyncOpenAI

        # 加载 LLM 任务配置
        cfg = LLMSelector.get_client_config("tender_parse")
        model = cfg["model"]
        temperature = LLMSelector.get_temperature("tender_parse")
        max_tokens = LLMSelector.get_max_tokens("tender_parse")

        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )

        chunks = _chunk_text(text)
        merged_result = {
            "project_name": None,
            "buyer_name": None,
            "customer_type": None,
            "budget_amount": None,
            "deadline": None,
            "tender_type": None,
            "delivery_scope": None,
            "disqualification_items": [],
            "qualification_requirements": [],
            "technical_requirements": [],
            "scoring_criteria": [],
            "commercial_requirements": [],
            "quotation_format": None,
        }

        for chunk in chunks:
            prompt = prompt_manager.format_prompt(
                "tender_parse", "v1_structured",
                tender_content=chunk,
            )

            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            resp_text = response.choices[0].message.content or ""
            try:
                chunk_result = _extract_json_from_response(resp_text)
            except (json.JSONDecodeError, ValueError):
                # 单块解析失败，跳过该块
                continue

            # 合并结果
            for field in ["project_name", "buyer_name", "customer_type",
                          "budget_amount", "deadline", "tender_type", "delivery_scope"]:
                if not merged_result[field] and chunk_result.get(field):
                    merged_result[field] = chunk_result[field]

            for list_field in ["disqualification_items", "qualification_requirements",
                               "technical_requirements", "scoring_criteria",
                               "commercial_requirements"]:
                items = chunk_result.get(list_field, [])
                if isinstance(items, list):
                    merged_result[list_field].extend(items)

            if not merged_result["quotation_format"] and chunk_result.get("quotation_format"):
                merged_result["quotation_format"] = chunk_result["quotation_format"]

        # 写入数据库
        await self._persist_parse_result(
            project_id, tenant_id, user_id, merged_result
        )

        return merged_result

    async def _persist_parse_result(
        self, project_id: int, tenant_id: int, user_id: int, result: dict
    ):
        """将解析结果持久化到数据库"""
        svc = BidProjectService(self.session)

        # 更新 BidProject 元数据
        project = await svc.get_project(project_id, tenant_id)
        if not project:
            raise ValueError("投标项目不存在")

        if result.get("buyer_name"):
            project.tender_org = result["buyer_name"]
        if result.get("customer_type"):
            project.customer_type = result["customer_type"]
        if result.get("tender_type"):
            project.tender_type = result["tender_type"]
        if result.get("budget_amount"):
            project.budget_amount = float(result["budget_amount"])
        if result.get("deadline"):
            project.deadline = result["deadline"]
        if result.get("delivery_scope"):
            project.delivery_scope = result["delivery_scope"]

        # 构建 TenderRequirement 列表
        requirements: list[TenderRequirementCreate] = []
        sort_order = 0

        # 废标项（最重要，排最前）
        for item in result.get("disqualification_items", []):
            sort_order += 1
            requirements.append(TenderRequirementCreate(
                category="disqualification",
                content=item.get("content", str(item)),
                is_mandatory=True,
                sort_order=sort_order,
            ))

        # 资格要求
        for item in result.get("qualification_requirements", []):
            sort_order += 1
            requirements.append(TenderRequirementCreate(
                category="qualification",
                content=item.get("content", str(item)),
                is_mandatory=item.get("is_mandatory", True),
                sort_order=sort_order,
            ))

        # 技术要求
        for item in result.get("technical_requirements", []):
            sort_order += 1
            requirements.append(TenderRequirementCreate(
                category="technical",
                content=item.get("content", str(item)),
                is_mandatory=True,
                sort_order=sort_order,
            ))

        # 评分标准
        for item in result.get("scoring_criteria", []):
            sort_order += 1
            requirements.append(TenderRequirementCreate(
                category="scoring",
                content=item.get("item", item.get("description", str(item))),
                is_mandatory=False,
                max_score=item.get("max_score"),
                score_weight=item.get("weight"),
                sort_order=sort_order,
            ))

        # 商务要求
        for item in result.get("commercial_requirements", []):
            sort_order += 1
            requirements.append(TenderRequirementCreate(
                category="commercial",
                content=item.get("content", str(item)),
                is_mandatory=True,
                sort_order=sort_order,
            ))

        # 批量写入
        if requirements:
            await svc.batch_create_requirements(
                project_id, tenant_id, requirements, user_id
            )

        # 更新项目状态
        project.status = BidProjectStatus.PARSED.value
        await self.session.commit()
