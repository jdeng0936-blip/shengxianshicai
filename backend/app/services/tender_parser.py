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
        raw_text = extract_tender_text(file_path, filename)
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
        task_config = LLMSelector.get_config("tender_parse")
        model = (task_config.get("models") or [settings.AI_MODEL])[0]
        temperature = task_config.get("temperature", 0.1)
        max_tokens = task_config.get("max_tokens", 4096)

        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL or None,
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
