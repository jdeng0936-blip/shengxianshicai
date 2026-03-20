"""
知识库 API 路由 — 工程案例 + 文档模板 + 章节片段
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.schemas.knowledge import (
    EngCaseCreate, EngCaseUpdate, EngCaseOut,
    DocTemplateCreate, DocTemplateOut,
    ChapterSnippetCreate, ChapterSnippetUpdate, ChapterSnippetOut,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["知识库"])


# ========== DAT-02 工程案例 ==========

@router.get("/cases", response_model=ApiResponse[list[EngCaseOut]])
async def list_cases(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    items = await svc.list_cases(tenant_id)
    return ApiResponse(data=[EngCaseOut.model_validate(i) for i in items])


@router.post("/cases", response_model=ApiResponse[EngCaseOut])
async def create_case(
    body: EngCaseCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    item = await svc.create_case(body, tenant_id, int(payload.get("sub", 0)))
    return ApiResponse(data=EngCaseOut.model_validate(item))


@router.put("/cases/{case_id}", response_model=ApiResponse[EngCaseOut])
async def update_case(
    case_id: int,
    body: EngCaseUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    svc = KnowledgeService(session)
    item = await svc.update_case(case_id, tenant_id, body)
    if not item:
        raise HTTPException(status_code=404, detail="案例不存在")
    return ApiResponse(data=EngCaseOut.model_validate(item))


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
                "content": r.get("content", "")[:500],
                "similarity": round(r.get("similarity", 0), 4),
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
                "content": r.get("content", "")[:500],
                "similarity": round(r.get("similarity", 0), 4),
            })
    except Exception:
        pass

    # 按相似度排序
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return ApiResponse(data=results[:top_k])

