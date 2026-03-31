"""
法规标准 API 路由 — StdDocument + StdClause CRUD + 文件上传解析向量化
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.schemas.standard import (
    StdDocumentCreate, StdDocumentUpdate, StdDocumentOut,
    StdClauseOut, StdClauseTree,
)
from app.services.standard_service import StandardService

router = APIRouter(prefix="/standards", tags=["法规标准"])


# ========== 文档 CRUD ==========

@router.get("", response_model=ApiResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    doc_type: Optional[str] = None,
    title: Optional[str] = None,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """法规标准列表（分页）"""
    svc = StandardService(session)
    items, total = await svc.list_documents(tenant_id, page, page_size, doc_type, title)
    return ApiResponse(data={"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/{doc_id}", response_model=ApiResponse)
async def get_document(
    doc_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取文档详情"""
    svc = StandardService(session)
    doc = await svc.get_document(doc_id, tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return ApiResponse(data=StdDocumentOut.model_validate(doc))


@router.get("/{doc_id}/clauses", response_model=ApiResponse[list[StdClauseTree]])
async def get_clause_tree(
    doc_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取文档条款树"""
    svc = StandardService(session)
    tree = await svc.get_clause_tree(doc_id)
    return ApiResponse(data=tree)


@router.delete("/{doc_id}", response_model=ApiResponse)
async def delete_document(
    doc_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除文档（级联删除条款）"""
    svc = StandardService(session)
    ok = await svc.delete_document(doc_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在")
    await session.commit()
    return ApiResponse(data={"deleted": True})


# ========== 文件上传 + 解析 + 向量化 ==========

@router.post("/detect-type", response_model=ApiResponse)
async def detect_document_type(
    file: UploadFile = File(...),
    payload: dict = Depends(get_current_user_payload),
):
    """从文件名和内容前500字自动识别文档类型和版本号"""
    import re
    filename = file.filename or ""
    content_bytes = await file.read()
    await file.seek(0)

    # 从文件名和内容推断
    name_lower = filename.lower()
    # 读取前500字用于分析
    try:
        import tempfile, os
        from app.services.document_parser import extract_text
        ext = os.path.splitext(filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content_bytes)
            tmp_path = tmp.name
        preview = extract_text(tmp_path, filename)[:800]
        os.unlink(tmp_path)
    except Exception:
        preview = ""

    combined = filename + " " + preview

    # 识别类型
    doc_type = "安全规程"
    if any(k in combined for k in ["食品安全法", "卫生法", "产品质量法", "GB 14881", "GB 31654"]):
        doc_type = "法律法规"
    elif any(k in combined for k in ["GB/T", "GB ", "国家标准", "行业标准", "冷链", "追溯", "包装"]):
        doc_type = "技术规范"
    elif any(k in combined for k in ["集团", "团体标准", "企业标准", "T/"]):
        doc_type = "集团标准"
    elif any(k in combined for k in ["政府采购", "招标投标", "采购法", "管理规定", "管理办法"]):
        doc_type = "法律法规"
    elif any(k in combined for k in ["操作规范", "规程", "安全", "卫生规范"]):
        doc_type = "安全规程"

    # 识别版本号
    version = ""
    # 匹配年份 (2019修订) 或 (2021) 或 -2019
    ver_match = re.search(r'[（(](\d{4})[年修订）)]*[）)]|[-—]\s*(\d{4})\b', combined)
    if ver_match:
        year = ver_match.group(1) or ver_match.group(2)
        version = year
    # 匹配 GB/T XXXXX-YYYY
    gb_match = re.search(r'GB/?T?\s*\d+[.-](\d{4})', combined)
    if gb_match:
        version = gb_match.group(1)
    # 匹配 v1.0 格式
    v_match = re.search(r'[vV](\d+\.\d+)', combined)
    if v_match:
        version = f"v{v_match.group(1)}"

    # 推荐标题（去掉扩展名）
    title = os.path.splitext(filename)[0] if filename else ""

    return ApiResponse(data={
        "doc_type": doc_type,
        "version": version,
        "title": title,
    })


@router.post("/upload", response_model=ApiResponse)
async def upload_standard(
    file: UploadFile = File(..., description="法规文件（DOC/DOCX/TXT）"),
    doc_type: str = Form("安全规程"),
    version: str = Form("v1.0"),
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """
    上传法规标准文件 → 提取章节结构 → 存入 StdDocument + StdClause → 向量化。
    支持 .doc / .docx / .txt 格式。
    """
    user_id = int(payload.get("sub", 0))
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".doc", ".docx", ".txt"):
        raise HTTPException(status_code=400, detail=f"不支持的格式: {ext}，仅支持 .doc/.docx/.txt")

    try:
        from app.services.document_parser import extract_text
        import tempfile
        import aiofiles
        import re

        # 保存临时文件
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # 提取文本
        raw_text = extract_text(tmp_path, filename)
        os.unlink(tmp_path)

        if not raw_text or len(raw_text.strip()) < 20:
            raise ValueError("文件内容为空或过短")

        # 创建文档记录
        svc = StandardService(session)
        doc_data = StdDocumentCreate(
            title=os.path.splitext(filename)[0],
            doc_type=doc_type,
            version=version,
        )
        doc = await svc.create_document(doc_data, tenant_id, user_id)

        # 按段落拆分为条款
        paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip() and len(p.strip()) > 10]

        # 尝试识别结构化条款（第X条、X.X 等模式）
        clause_pattern = re.compile(
            r'^(第[一二三四五六七八九十百千]+条|'
            r'\d+\.\d+(?:\.\d+)?|'
            r'第[一二三四五六七八九十百千]+[章节篇])'
        )

        clause_count = 0
        current_title = ""
        current_content_parts = []

        def flush_clause():
            nonlocal clause_count, current_title, current_content_parts
            if current_content_parts:
                from app.models.standard import StdClause as StdClauseModel
                content_text = "\n".join(current_content_parts)
                clause = StdClauseModel(
                    document_id=doc.id,
                    clause_no=current_title[:30] if current_title else None,
                    title=current_title[:200] if current_title else None,
                    content=content_text,
                    level=0,
                )
                session.add(clause)
                clause_count += 1
                current_content_parts.clear()
                current_title = ""

        for para in paragraphs:
            match = clause_pattern.match(para)
            if match:
                flush_clause()
                current_title = para[:200]
                current_content_parts.append(para)
            else:
                current_content_parts.append(para)

        flush_clause()

        # 如果没有识别到结构化条款，按每段作为一个条款
        if clause_count == 0:
            from app.models.standard import StdClause as StdClauseModel
            for i, para in enumerate(paragraphs):
                clause = StdClauseModel(
                    document_id=doc.id,
                    content=para,
                    level=0,
                )
                session.add(clause)
                clause_count += 1

        await session.commit()

        # 向量化
        vectorized_count = 0
        try:
            from app.services.embedding_service import EmbeddingService
            from sqlalchemy import select
            from app.models.standard import StdClause as StdClauseModel

            emb_svc = EmbeddingService(session)
            result = await session.execute(
                select(StdClauseModel).where(
                    StdClauseModel.document_id == doc.id,
                    StdClauseModel.embedding.is_(None),
                )
            )
            clauses = list(result.scalars().all())

            batch_size = 10
            for i in range(0, len(clauses), batch_size):
                batch = clauses[i:i + batch_size]
                texts = [f"{c.title or ''} {c.content or ''}" for c in batch]
                embeddings = await emb_svc.embed_batch(texts)
                for clause, emb in zip(batch, embeddings):
                    if emb is not None:
                        clause.embedding = emb
                        vectorized_count += 1
                await session.commit()
        except Exception:
            pass  # 向量化失败不阻塞上传

        return ApiResponse(data={
            "doc_id": doc.id,
            "clause_count": clause_count,
            "vectorized_count": vectorized_count,
        })

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"法规文件解析失败: {str(e)}")
