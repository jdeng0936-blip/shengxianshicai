"""
投标项目 API 路由 — BidProject + TenderRequirement + BidChapter CRUD + 招标文件上传解析 + AI 生成
"""
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.schemas.bid_project import (
    BidProjectCreate, BidProjectUpdate, BidProjectOut, BidProjectListOut,
    TenderRequirementCreate, TenderRequirementUpdate, TenderRequirementOut,
    BidChapterCreate, BidChapterUpdate, BidChapterOut,
)
from app.services.bid_project_service import BidProjectService
from app.services.tender_parser import TenderParseService
from app.services.bid_generation_service import BidGenerationService

router = APIRouter(prefix="/bid-projects", tags=["投标项目"])


# ========== BidProject CRUD ==========

@router.get("", response_model=ApiResponse[list[BidProjectListOut]])
async def list_projects(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取投标项目列表"""
    svc = BidProjectService(session)
    items = await svc.list_projects(tenant_id)
    return ApiResponse(data=[BidProjectListOut.model_validate(p) for p in items])


@router.get("/{project_id}", response_model=ApiResponse[BidProjectOut])
async def get_project(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取投标项目详情（含招标要求和章节）"""
    svc = BidProjectService(session)
    project = await svc.get_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="投标项目不存在")
    return ApiResponse(data=BidProjectOut.model_validate(project))


@router.post("", response_model=ApiResponse[BidProjectOut])
async def create_project(
    body: BidProjectCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """创建投标项目"""
    user_id = int(payload.get("sub", 0))
    svc = BidProjectService(session)
    project = await svc.create_project(body, tenant_id, user_id)
    return ApiResponse(data=BidProjectOut.model_validate(project))


@router.put("/{project_id}", response_model=ApiResponse[BidProjectOut])
async def update_project(
    project_id: int,
    body: BidProjectUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """更新投标项目"""
    svc = BidProjectService(session)
    project = await svc.update_project(project_id, tenant_id, body)
    if not project:
        raise HTTPException(status_code=404, detail="投标项目不存在")
    return ApiResponse(data=BidProjectOut.model_validate(project))


@router.delete("/{project_id}", response_model=ApiResponse)
async def delete_project(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除投标项目（级联删除关联数据）"""
    svc = BidProjectService(session)
    ok = await svc.delete_project(project_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="投标项目不存在")
    return ApiResponse(data={"deleted": True})


# ========== 招标文件上传与解析 ==========

@router.post("/{project_id}/upload-tender", response_model=ApiResponse)
async def upload_tender(
    project_id: int,
    file: UploadFile = File(..., description="招标文件（PDF/DOCX/DOC）"),
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """上传招标文件"""
    user_id = int(payload.get("sub", 0))

    # 校验项目存在
    svc = BidProjectService(session)
    project = await svc.get_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="投标项目不存在")

    try:
        parser = TenderParseService(session)
        file_path, filename = await parser.save_tender_file(project_id, tenant_id, file)

        # 更新项目的招标文件路径
        project.tender_doc_path = file_path
        await session.commit()

        return ApiResponse(data={
            "file_path": file_path,
            "filename": filename,
            "message": "招标文件上传成功，可调用解析接口进行 AI 解析",
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{project_id}/parse-tender", response_model=ApiResponse)
async def parse_tender(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """AI 解析招标文件 — 提取结构化要求（废标项/资格要求/评分标准等）"""
    user_id = int(payload.get("sub", 0))

    # 校验项目存在且有招标文件
    svc = BidProjectService(session)
    project = await svc.get_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="投标项目不存在")
    if not project.tender_doc_path:
        raise HTTPException(status_code=400, detail="请先上传招标文件")

    try:
        # 更新状态为解析中
        project.status = "parsing"
        await session.commit()

        parser = TenderParseService(session)

        # 1. 提取文本
        text = await parser.extract_text(
            project.tender_doc_path,
            project.tender_doc_path.split("/")[-1],
        )

        # 2. LLM 结构化解析
        result = await parser.parse_with_llm(project_id, tenant_id, text, user_id)

        return ApiResponse(data={
            "status": "parsed",
            "requirements_count": sum(
                len(result.get(k, []))
                for k in ["disqualification_items", "qualification_requirements",
                          "technical_requirements", "scoring_criteria",
                          "commercial_requirements"]
            ),
            "project_name": result.get("project_name"),
            "buyer_name": result.get("buyer_name"),
            "customer_type": result.get("customer_type"),
            "budget_amount": result.get("budget_amount"),
        })
    except Exception as e:
        # 解析失败，更新状态
        project.status = "failed"
        await session.commit()
        raise HTTPException(status_code=500, detail=f"招标文件解析失败: {str(e)}")


@router.patch("/{project_id}/status", response_model=ApiResponse[BidProjectOut])
async def update_status(
    project_id: int,
    status: str,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """更新投标项目状态"""
    svc = BidProjectService(session)
    project = await svc.update_status(project_id, tenant_id, status)
    if not project:
        raise HTTPException(status_code=404, detail="投标项目不存在")
    return ApiResponse(data=BidProjectOut.model_validate(project))


# ========== TenderRequirement CRUD ==========

@router.get("/{project_id}/requirements", response_model=ApiResponse[list[TenderRequirementOut]])
async def list_requirements(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取招标要求列表"""
    svc = BidProjectService(session)
    items = await svc.list_requirements(project_id, tenant_id)
    return ApiResponse(data=[TenderRequirementOut.model_validate(r) for r in items])


@router.post("/{project_id}/requirements", response_model=ApiResponse[TenderRequirementOut])
async def create_requirement(
    project_id: int,
    body: TenderRequirementCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """创建招标要求"""
    user_id = int(payload.get("sub", 0))
    svc = BidProjectService(session)
    req = await svc.create_requirement(project_id, tenant_id, body, user_id)
    if not req:
        raise HTTPException(status_code=404, detail="投标项目不存在")
    return ApiResponse(data=TenderRequirementOut.model_validate(req))


@router.post(
    "/{project_id}/requirements/batch",
    response_model=ApiResponse[list[TenderRequirementOut]],
)
async def batch_create_requirements(
    project_id: int,
    body: List[TenderRequirementCreate],
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """批量创建招标要求（招标文件解析后使用）"""
    user_id = int(payload.get("sub", 0))
    svc = BidProjectService(session)
    reqs = await svc.batch_create_requirements(project_id, tenant_id, body, user_id)
    return ApiResponse(data=[TenderRequirementOut.model_validate(r) for r in reqs])


@router.put("/requirements/{req_id}", response_model=ApiResponse[TenderRequirementOut])
async def update_requirement(
    req_id: int,
    body: TenderRequirementUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """更新招标要求"""
    svc = BidProjectService(session)
    req = await svc.update_requirement(req_id, tenant_id, body)
    if not req:
        raise HTTPException(status_code=404, detail="招标要求不存在")
    return ApiResponse(data=TenderRequirementOut.model_validate(req))


@router.delete("/requirements/{req_id}", response_model=ApiResponse)
async def delete_requirement(
    req_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除招标要求"""
    svc = BidProjectService(session)
    ok = await svc.delete_requirement(req_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="招标要求不存在")
    return ApiResponse(data={"deleted": True})


# ========== BidChapter CRUD ==========

@router.get("/{project_id}/chapters", response_model=ApiResponse[list[BidChapterOut]])
async def list_chapters(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取投标章节列表"""
    svc = BidProjectService(session)
    items = await svc.list_chapters(project_id, tenant_id)
    return ApiResponse(data=[BidChapterOut.model_validate(c) for c in items])


@router.post("/{project_id}/chapters", response_model=ApiResponse[BidChapterOut])
async def create_chapter(
    project_id: int,
    body: BidChapterCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """创建投标章节"""
    user_id = int(payload.get("sub", 0))
    svc = BidProjectService(session)
    chapter = await svc.create_chapter(project_id, tenant_id, body, user_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="投标项目不存在")
    return ApiResponse(data=BidChapterOut.model_validate(chapter))


@router.put("/chapters/{chapter_id}", response_model=ApiResponse[BidChapterOut])
async def update_chapter(
    chapter_id: int,
    body: BidChapterUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """更新投标章节"""
    svc = BidProjectService(session)
    chapter = await svc.update_chapter(chapter_id, tenant_id, body)
    if not chapter:
        raise HTTPException(status_code=404, detail="投标章节不存在")
    return ApiResponse(data=BidChapterOut.model_validate(chapter))


@router.delete("/chapters/{chapter_id}", response_model=ApiResponse)
async def delete_chapter(
    chapter_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除投标章节"""
    svc = BidProjectService(session)
    ok = await svc.delete_chapter(chapter_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="投标章节不存在")
    return ApiResponse(data={"deleted": True})


# ========== AI 章节生成 ==========

@router.post("/{project_id}/init-chapters", response_model=ApiResponse[list[BidChapterOut]])
async def init_chapters(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """根据模板初始化投标文件章节结构"""
    user_id = int(payload.get("sub", 0))
    gen_svc = BidGenerationService(session)
    try:
        chapters = await gen_svc.init_chapters(project_id, tenant_id, user_id)
        return ApiResponse(data=[BidChapterOut.model_validate(ch) for ch in chapters])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{project_id}/generate-chapter/{chapter_id}", response_model=ApiResponse[BidChapterOut])
async def generate_chapter(
    project_id: int,
    chapter_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """AI 生成单个投标章节内容"""
    gen_svc = BidGenerationService(session)
    try:
        chapter = await gen_svc.generate_single_chapter(project_id, chapter_id, tenant_id)
        return ApiResponse(data=BidChapterOut.model_validate(chapter))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"章节生成失败: {str(e)}")


@router.post("/{project_id}/generate-all")
async def generate_all_chapters(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """AI 批量生成所有投标章节（SSE 流式报告进度）"""
    user_id = int(payload.get("sub", 0))
    gen_svc = BidGenerationService(session)

    async def event_stream():
        try:
            async for progress in gen_svc.generate_all_chapters(project_id, tenant_id, user_id):
                yield f"data: {json.dumps(progress, ensure_ascii=False)}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'生成失败: {str(e)}'}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
