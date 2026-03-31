"""
知识库 API 路由 — 工程案例 + 文档模板 + 章节片段 + 优选标书上传
"""
import os
import re
import tempfile

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.schemas.knowledge import (
    BidCaseCreate, BidCaseUpdate, BidCaseOut,
    DocTemplateCreate, DocTemplateOut,
    ChapterSnippetCreate, ChapterSnippetUpdate, ChapterSnippetOut,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["知识库"])


# ========== DAT-02 工程案例 ==========

@router.get("/cases", response_model=ApiResponse[list[BidCaseOut]])
async def list_cases(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    items = await svc.list_cases(tenant_id)
    return ApiResponse(data=[BidCaseOut.model_validate(i) for i in items])


@router.post("/cases", response_model=ApiResponse[BidCaseOut])
async def create_case(
    body: BidCaseCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    item = await svc.create_case(body, tenant_id, int(payload.get("sub", 0)))
    return ApiResponse(data=BidCaseOut.model_validate(item))


@router.put("/cases/{case_id}", response_model=ApiResponse[BidCaseOut])
async def update_case(
    case_id: int,
    body: BidCaseUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    item = await svc.update_case(case_id, tenant_id, body)
    if not item:
        raise HTTPException(status_code=404, detail="案例不存在")
    return ApiResponse(data=BidCaseOut.model_validate(item))


@router.delete("/cases/{case_id}", response_model=ApiResponse)
async def delete_case(
    case_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    ok = await svc.delete_case(case_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="案例不存在")
    return ApiResponse(data={"deleted": True})


# ========== DAT-03 文档模板 ==========

@router.get("/templates", response_model=ApiResponse[list[DocTemplateOut]])
async def list_templates(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    items = await svc.list_templates(tenant_id)
    return ApiResponse(data=[DocTemplateOut.model_validate(i) for i in items])


@router.post("/templates", response_model=ApiResponse[DocTemplateOut])
async def create_template(
    body: DocTemplateCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    item = await svc.create_template(body, tenant_id, int(payload.get("sub", 0)))
    return ApiResponse(data=DocTemplateOut.model_validate(item))


@router.delete("/templates/{tpl_id}", response_model=ApiResponse)
async def delete_template(
    tpl_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    ok = await svc.delete_template(tpl_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="模板不存在")
    return ApiResponse(data={"deleted": True})


# ========== DAT-04 章节片段 ==========

@router.get("/snippets", response_model=ApiResponse[list[ChapterSnippetOut]])
async def list_snippets(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    items = await svc.list_snippets(tenant_id)
    return ApiResponse(data=[ChapterSnippetOut.model_validate(i) for i in items])


@router.post("/snippets", response_model=ApiResponse[ChapterSnippetOut])
async def create_snippet(
    body: ChapterSnippetCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    item = await svc.create_snippet(body, tenant_id, int(payload.get("sub", 0)))
    return ApiResponse(data=ChapterSnippetOut.model_validate(item))


@router.put("/snippets/{snp_id}", response_model=ApiResponse[ChapterSnippetOut])
async def update_snippet(
    snp_id: int,
    body: ChapterSnippetUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    item = await svc.update_snippet(snp_id, tenant_id, body)
    if not item:
        raise HTTPException(status_code=404, detail="片段不存在")
    return ApiResponse(data=ChapterSnippetOut.model_validate(item))


@router.delete("/snippets/{snp_id}", response_model=ApiResponse)
async def delete_snippet(
    snp_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    ok = await svc.delete_snippet(snp_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="片段不存在")
    return ApiResponse(data={"deleted": True})


# ========== 优选标书上传（切片为知识片段 + 向量化） ==========

@router.post("/bid-docs/upload", response_model=ApiResponse)
async def upload_bid_document(
    file: UploadFile = File(..., description="历史中标标书（PDF/DOCX/DOC）"),
    project_name: str = Form(""),
    customer_type: str = Form(""),
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """
    上传优选标书 → 提取全文 → 按章节切片 → 存入 ChapterSnippet → 向量化。
    用于 RAG 检索，为后续标书生成提供高质量参考。
    """
    user_id = int(payload.get("sub", 0))
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc", ".txt"):
        raise HTTPException(status_code=400, detail=f"不支持的格式: {ext}，仅支持 PDF/DOCX/DOC/TXT")

    try:
        from app.services.document_parser import extract_text
        from app.services.tender_parser import extract_text_from_pdf

        # 保存临时文件
        content = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # 提取文本
        if ext == ".pdf":
            raw_text = extract_text_from_pdf(tmp_path)
        else:
            raw_text = extract_text(tmp_path, filename)
        os.unlink(tmp_path)

        if not raw_text or len(raw_text.strip()) < 50:
            raise ValueError("文件内容为空或过短")

        # 按章节标题切片
        chapter_pattern = re.compile(
            r'^(第[一二三四五六七八九十]+[章节][\s\S]{0,50}|'
            r'\d{1,2}[\.、]\s*[\u4e00-\u9fff]{2,20})',
            re.MULTILINE
        )

        # 分割为章节
        splits = chapter_pattern.split(raw_text)
        chunks = []
        current_title = project_name or os.path.splitext(filename)[0]
        current_no = "1"
        chapter_idx = 0

        for i, part in enumerate(splits):
            part = part.strip()
            if not part:
                continue
            if chapter_pattern.match(part):
                current_title = part[:100]
                chapter_idx += 1
                current_no = str(chapter_idx)
            elif len(part) > 50:
                chunks.append({
                    "chapter_no": current_no,
                    "chapter_name": current_title,
                    "content": part[:3000],
                })

        # 如果没有识别到章节，按段落切片（每 1500 字一片）
        if not chunks:
            paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip() and len(p.strip()) > 30]
            current_chunk = ""
            chunk_idx = 0
            for para in paragraphs:
                if len(current_chunk) + len(para) > 1500 and current_chunk:
                    chunk_idx += 1
                    chunks.append({
                        "chapter_no": str(chunk_idx),
                        "chapter_name": f"{os.path.splitext(filename)[0]}-片段{chunk_idx}",
                        "content": current_chunk,
                    })
                    current_chunk = para
                else:
                    current_chunk += "\n\n" + para if current_chunk else para
            if current_chunk and len(current_chunk) > 30:
                chunk_idx += 1
                chunks.append({
                    "chapter_no": str(chunk_idx),
                    "chapter_name": f"{os.path.splitext(filename)[0]}-片段{chunk_idx}",
                    "content": current_chunk,
                })

        # 写入 ChapterSnippet
        from app.models.document import ChapterSnippet

        snippet_count = 0
        for chunk in chunks:
            snippet = ChapterSnippet(
                chapter_no=chunk["chapter_no"],
                chapter_name=chunk["chapter_name"],
                content=chunk["content"],
                customer_type=customer_type or None,
                sort_order=snippet_count,
                tenant_id=tenant_id,
                created_by=user_id,
            )
            session.add(snippet)
            snippet_count += 1

        await session.commit()

        # 向量化
        vectorized_count = 0
        try:
            from app.services.embedding_service import EmbeddingService
            from sqlalchemy import select

            emb_svc = EmbeddingService(session)
            result = await session.execute(
                select(ChapterSnippet).where(
                    ChapterSnippet.tenant_id == tenant_id,
                    ChapterSnippet.created_by == user_id,
                    ChapterSnippet.embedding.is_(None),
                ).order_by(ChapterSnippet.id.desc()).limit(snippet_count)
            )
            new_snippets = list(result.scalars().all())

            batch_size = 10
            for i in range(0, len(new_snippets), batch_size):
                batch = new_snippets[i:i + batch_size]
                texts = [f"{s.chapter_name} {s.content}" for s in batch]
                embeddings = await emb_svc.embed_batch(texts)
                for snippet, emb in zip(batch, embeddings):
                    if emb is not None:
                        snippet.embedding = emb
                        vectorized_count += 1
                await session.commit()
        except Exception:
            pass

        return ApiResponse(data={
            "filename": filename,
            "snippet_count": snippet_count,
            "vectorized_count": vectorized_count,
        })

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标书解析失败: {str(e)}")


# ========== 语义搜索（向量检索） ==========

@router.get("/search", response_model=ApiResponse)
async def semantic_search(
    q: str,
    top_k: int = 10,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """语义搜索 — 同时搜索标准库条款 + 知识库片段，按相似度排序返回"""
    from app.services.embedding_service import EmbeddingService
    emb = EmbeddingService(session)

    results = []

    # 搜索标准库条款
    try:
        std_hits = await emb.search_similar(query=q, tenant_id=tenant_id, top_k=top_k, threshold=0.3)
        for r in (std_hits or []):
            results.append({
                "type": "标准条款",
                "title": r.get("doc_title", ""),
                "clause_no": r.get("clause_no", ""),
                "content": r.get("content", ""),
                "distance": round(r.get("distance", 1), 4),
            })
    except Exception:
        pass

    # 搜索知识库片段
    try:
        snp_hits = await emb.search_snippets(query=q, tenant_id=tenant_id, top_k=top_k, threshold=0.3)
        for r in (snp_hits or []):
            results.append({
                "type": "知识片段",
                "title": r.get("chapter_name", ""),
                "clause_no": "",
                "content": r.get("content", ""),
                "distance": round(r.get("distance", 1), 4),
            })
    except Exception:
        pass

    # 按距离排序（越小越相似）
    results.sort(key=lambda x: x["distance"])
    return ApiResponse(data=results[:top_k])

