"""
投标项目 API 路由 — BidProject + TenderRequirement + BidChapter CRUD + 招标文件上传解析 + AI 生成 + 导出
"""
import asyncio
import json
import logging
import os
import uuid as _uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session, async_session_factory
from app.core.deps import get_current_user_payload, get_tenant_id
from app.core.redis import get_redis
from app.core.task_store import ParseTaskStore, FullParseGuard
from app.schemas.common import ApiResponse
from app.schemas.bid_project import (
    BidProjectCreate, BidProjectUpdate, BidProjectOut, BidProjectListOut,
    TenderRequirementCreate, TenderRequirementUpdate, TenderRequirementOut,
    BidChapterCreate, BidChapterUpdate, BidChapterOut,
)
from app.services.bid_project_service import BidProjectService
from app.services.tender_parser import TenderParseService
from app.services.bid_generation_service import BidGenerationService
from app.services.bid_doc_exporter import BidDocExporter
from app.services.bid_compliance_service import BidComplianceService
from app.services.bid_quotation_service import BidQuotationService
from app.services.risk_report_service import RiskReportService
from app.schemas.quotation import QuotationSheetOut

logger = logging.getLogger("freshbid")

router = APIRouter(prefix="/bid-projects", tags=["投标项目"])

# ---------- Redis 任务存储辅助 ----------

def _task_store() -> ParseTaskStore:
    return ParseTaskStore(get_redis())


async def _run_full_parse(project_id: int, tenant_id: int, user_id: int = 0):
    """后台协程：对已关联招标文件的项目执行完整结构化解析（独立 session）

    加固点：
    - Redis 分布式锁防重入（同一项目不会被并发解析）
    - TTL 自动释放（进程崩溃不会死锁）
    - 解析状态写入 Redis 供查询
    """
    await asyncio.sleep(0)

    guard = FullParseGuard(get_redis(), project_id)

    # 获取锁，失败说明已有解析在跑
    if not await guard.acquire():
        logger.warning(f"跳过重复解析: project_id={project_id} 已在解析中")
        return

    try:
        await guard.set_state("parsing")

        async with async_session_factory() as session:
            svc = BidProjectService(session)
            project = await svc.get_project(project_id, tenant_id)
            if not project or not project.tender_doc_path:
                logger.warning(f"自动解析跳过: project_id={project_id} 无招标文件")
                await guard.set_state("skipped", "无招标文件")
                return

            project.status = "parsing"
            await session.commit()

            parser = TenderParseService(session)
            text = await parser.extract_text(
                project.tender_doc_path,
                project.tender_doc_path.split("/")[-1],
            )
            result = await parser.parse_with_llm(project_id, tenant_id, text, user_id)

            req_count = sum(
                len(result.get(k, []))
                for k in ["disqualification_items", "qualification_requirements",
                          "technical_requirements", "scoring_criteria",
                          "commercial_requirements"]
            )
            await guard.set_state("parsed", f"提取招标要求 {req_count} 条")
            logger.info(f"自动解析完成: project_id={project_id}, 提取招标要求 {req_count} 条")
    except Exception as e:
        # 解析失败不抛异常，仅更新状态和记录日志
        await guard.set_state("failed", str(e))
        try:
            async with async_session_factory() as session:
                svc = BidProjectService(session)
                project = await svc.get_project(project_id, tenant_id)
                if project:
                    project.status = "failed"
                    await session.commit()
        except Exception:
            pass
        logger.error(f"自动解析失败: project_id={project_id}: {e}")
    finally:
        await guard.release()


async def _run_preview_parse(task_id: str, temp_path: str, filename: str):
    """后台协程：执行招标文件预览解析并将结果写入 Redis"""
    await asyncio.sleep(0)
    store = _task_store()
    try:
        result = await TenderParseService.preview_parse(temp_path, filename)
        await store.set_done(task_id, {
            **result,
            "temp_file_path": temp_path,
            "filename": filename,
        })
        logger.info(f"预览解析任务完成 task_id={task_id}")
    except Exception as e:
        await store.set_error(task_id, str(e))
        logger.error(f"预览解析任务失败 task_id={task_id}: {e}")


# ========== Dashboard 统计 ==========

@router.get("/dashboard/stats", response_model=ApiResponse)
async def dashboard_stats(
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """Dashboard 聚合统计（服务端计算，避免前端全量拉取）"""
    from sqlalchemy import select as sa_select, func, case
    from app.models.bid_project import BidProject

    q = sa_select(
        func.count().label("total"),
        func.sum(case((BidProject.status.in_(["parsing", "parsed", "generating", "generated", "reviewing"]), 1), else_=0)).label("in_progress"),
        func.sum(case((BidProject.status.in_(["completed", "submitted", "won"]), 1), else_=0)).label("completed"),
        func.sum(case((BidProject.status == "won", 1), else_=0)).label("won"),
        func.sum(case((BidProject.status == "lost", 1), else_=0)).label("lost"),
        func.coalesce(func.sum(BidProject.budget_amount), 0).label("total_budget"),
    ).where(BidProject.tenant_id == tenant_id)

    result = await session.execute(q)
    row = result.one()

    return ApiResponse(data={
        "total": row.total or 0,
        "in_progress": int(row.in_progress or 0),
        "completed": int(row.completed or 0),
        "won": int(row.won or 0),
        "lost": int(row.lost or 0),
        "total_budget": float(row.total_budget or 0),
    })


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


# ========== 招标文件预览解析（异步任务 + 轮询模式） ==========

@router.post("/preview-tender", response_model=ApiResponse)
async def preview_tender(
    file: UploadFile = File(..., description="招标文件（PDF/DOCX/DOC）"),
    payload: dict = Depends(get_current_user_payload),
):
    """
    上传招标文件并启动异步预览解析任务。
    立即返回 task_id，前端通过轮询 /preview-tender/{task_id}/status 获取结果。
    """
    try:
        # 保存到临时目录（毫秒级）
        temp_path, filename = await TenderParseService.save_temp_file(file)

        # 生成任务 ID 并注册到 Redis
        task_id = _uuid.uuid4().hex
        await _task_store().create(task_id)

        # 后台启动异步解析（不阻塞当前请求）
        asyncio.create_task(_run_preview_parse(task_id, temp_path, filename))

        return ApiResponse(data={
            "task_id": task_id,
            "status": "pending",
            "message": "文件已上传，AI 解析已在后台启动",
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@router.get("/preview-tender/{task_id}/status", response_model=ApiResponse)
async def preview_tender_status(
    task_id: str,
    payload: dict = Depends(get_current_user_payload),
):
    """
    查询招标文件预览解析任务状态。
    返回 status: pending（进行中）/ done（完成）/ error（失败）。
    """
    task = await _task_store().get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="解析任务不存在或已过期")

    return ApiResponse(data={
        "task_id": task_id,
        "status": task["status"],
        "data": task.get("data"),
        "error": task.get("error"),
    })


# ========== 关联预览时上传的招标文件 ==========

from pydantic import BaseModel as _PydanticBase


class AssociateTenderRequest(_PydanticBase):
    temp_file_path: str


@router.post("/{project_id}/associate-tender", response_model=ApiResponse)
async def associate_tender(
    project_id: int,
    body: AssociateTenderRequest,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """将预览时上传的临时招标文件关联到项目，并自动触发后台结构化解析"""
    import shutil
    from pathlib import Path

    svc = BidProjectService(session)
    project = await svc.get_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="投标项目不存在")

    temp_path = Path(body.temp_file_path)
    if not temp_path.exists() or "_temp" not in str(temp_path):
        raise HTTPException(status_code=400, detail="临时文件不存在或路径无效")

    # 移动到项目目录
    dest_dir = Path(f"storage/tenders/{tenant_id}/{project_id}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / temp_path.name
    shutil.move(str(temp_path), str(dest_path))

    project.tender_doc_path = str(dest_path)
    await session.commit()

    # 后台自动触发结构化解析（不阻塞响应）
    user_id = int(payload.get("sub", 0))
    asyncio.create_task(_run_full_parse(project_id, tenant_id, user_id))
    logger.info(f"关联招标文件并启动自动解析: project_id={project_id}")

    return ApiResponse(data={
        "file_path": str(dest_path),
        "message": "招标文件已关联到项目，AI 解析已在后台启动",
    })


# ========== 招标文件上传与解析 ==========

@router.post("/{project_id}/upload-tender", response_model=ApiResponse)
async def upload_tender(
    project_id: int,
    file: UploadFile = File(..., description="招标文件（PDF/DOCX/DOC）"),
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """上传招标文件（上传完成后自动触发后台 AI 结构化解析）"""
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

        # 后台自动触发结构化解析（不阻塞响应）
        asyncio.create_task(_run_full_parse(project_id, tenant_id, user_id))
        logger.info(f"上传招标文件并启动自动解析: project_id={project_id}")

        return ApiResponse(data={
            "file_path": file_path,
            "filename": filename,
            "message": "招标文件上传成功，AI 解析已在后台自动启动",
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


@router.post("/{project_id}/generate-chapter/{chapter_id}/stream")
async def generate_chapter_stream(
    project_id: int,
    chapter_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """AI 流式生成单个投标章节（SSE 打字机效果 + 阶段状态推送）"""
    from app.services.bid_generation_service import BidGenerationService
    gen_svc = BidGenerationService(session)

    async def event_stream():
        try:
            async for event in gen_svc.generate_single_chapter_stream(
                project_id, chapter_id, tenant_id
            ):
                yield event
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


# ========== 投标文件导出 ==========

@router.post("/{project_id}/export", response_model=ApiResponse)
async def export_bid_doc(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """导出投标文件为 Word 文档"""
    exporter = BidDocExporter(session)
    try:
        file_path = await exporter.export(project_id, tenant_id)
        filename = os.path.basename(file_path)
        return ApiResponse(data={
            "file_path": file_path,
            "filename": filename,
            "message": "投标文件导出成功",
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/{project_id}/export-check", response_model=ApiResponse)
async def export_check(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """导出前检查 — 返回致命风险项列表和是否可导出"""
    risk_svc = RiskReportService(session)
    try:
        report = await risk_svc.generate_report(project_id, tenant_id)
        fatal_items = [r for r in report["risks"] if r["level"] == "fatal"]
        return ApiResponse(data={
            "can_export": len(fatal_items) == 0,
            "fatal_count": len(fatal_items),
            "fatal_items": fatal_items,
            "disclaimer": "本文件由 AI 辅助生成，仅供参考。投标人应对内容的准确性、完整性和合规性承担最终责任。",
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{project_id}/download")
async def download_bid_doc(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """下载已生成的投标文件"""
    svc = BidProjectService(session)
    project = await svc.get_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="投标项目不存在")
    if not project.bid_doc_path or not os.path.exists(project.bid_doc_path):
        raise HTTPException(status_code=404, detail="投标文件尚未生成，请先导出")

    filename = os.path.basename(project.bid_doc_path)
    return FileResponse(
        path=project.bid_doc_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ========== 合规检查 ==========

@router.post("/{project_id}/compliance-check", response_model=ApiResponse)
async def compliance_check(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """废标项 + 资格 + 评分覆盖合规检查"""
    svc = BidComplianceService(session)
    try:
        result = await svc.check(project_id, tenant_id)
        return ApiResponse(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合规检查失败: {str(e)}")


# ========== 报价单自动初始化 ==========

@router.post("/{project_id}/init-quotation", response_model=ApiResponse[QuotationSheetOut])
async def init_quotation(
    project_id: int,
    discount_rate: float | None = None,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """根据招标要求自动初始化报价单（预填六大品类常见食材 + 参考价）"""
    user_id = int(payload.get("sub", 0))
    svc = BidQuotationService(session)
    try:
        sheet = await svc.init_quotation(project_id, tenant_id, user_id, discount_rate)
        return ApiResponse(data=QuotationSheetOut.model_validate(sheet))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"报价单初始化失败: {str(e)}")


# ========== AI 选段重写 ==========

from pydantic import BaseModel as _BaseModel, Field as _Field


class RewriteRequest(_BaseModel):
    text: str = _Field(min_length=1, description="选中的文本")
    action: str = _Field("polish", description="操作: polish/expand/condense/rewrite")
    context: Optional[str] = _Field(None, description="章节标题等上下文")


class ChapterRewriteRequest(_BaseModel):
    """章节局部重写请求 — 支持自定义指令"""
    original_text: str = _Field(min_length=1, description="被选中的原文本")
    instruction: str = _Field(min_length=1, description="改写指令，如「语气改正式一点」「削减篇幅」「补充数据支撑」")


@router.post("/{project_id}/rewrite-selection", response_model=ApiResponse)
async def rewrite_selection(
    project_id: int,
    body: RewriteRequest,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """AI 重写选中文本（润色/扩写/精简/重写）"""
    from openai import AsyncOpenAI
    from app.core.llm_selector import LLMSelector

    action_prompts = {
        "polish": "请润色以下投标文件段落，使其更专业、更通顺，保持原意不变：",
        "expand": "请扩写以下投标文件段落，补充具体细节、数据和措施，使内容更充实（扩展到原文2倍左右）：",
        "condense": "请精简以下投标文件段落，去除冗余表述，保留核心要点，压缩到原文50%左右：",
        "rewrite": "请重写以下投标文件段落，保持主题不变但换一种更有说服力的表达方式：",
    }

    prompt_prefix = action_prompts.get(body.action, action_prompts["polish"])
    context_hint = f"\n\n所属章节：{body.context}" if body.context else ""

    prompt = f"""{prompt_prefix}{context_hint}

---
{body.text}
---

要求：
- 使用专业的投标文件用语
- 输出纯文本，不要加任何解释说明
- 保持 Markdown 格式（如有标题、列表等）"""

    try:
        cfg = LLMSelector.get_client_config("bid_section_generate")
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )
        response = await client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=4096,
        )
        result_text = response.choices[0].message.content or ""
        return ApiResponse(data={
            "original": body.text,
            "rewritten": result_text,
            "action": body.action,
            "model": cfg["model"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 重写失败: {str(e)}")


@router.post("/{project_id}/chapters/{chapter_id}/rewrite", response_model=ApiResponse)
async def rewrite_chapter_segment(
    project_id: int,
    chapter_id: int,
    body: ChapterRewriteRequest,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """章节局部重写 — 用户提供自定义改写指令

    不直接修改 DB，返回重写后的文本片段供前端替换选区。
    """
    from openai import AsyncOpenAI
    from app.core.llm_selector import LLMSelector

    # 加载章节标题作为上下文
    from app.services.bid_project_service import BidProjectService
    svc = BidProjectService(session)
    project = await svc.get_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    chapter = next((ch for ch in project.chapters if ch.id == chapter_id), None)
    chapter_context = f"{chapter.chapter_no} {chapter.title}" if chapter else ""

    prompt = (
        f"你是资深的投标文件修改专家。请按照用户的指令对以下投标文件段落进行改写。\n\n"
        f"== 用户指令 ==\n{body.instruction}\n\n"
        f"== 所属章节 ==\n{chapter_context}\n\n"
        f"== 原文 ==\n{body.original_text}\n\n"
        f"要求：\n"
        f"- 严格按照用户指令改写，不偏离指令意图\n"
        f"- 使用专业的投标文件用语\n"
        f"- 保持 Markdown 格式\n"
        f"- 只输出改写后的文本，不加任何解释说明"
    )

    try:
        cfg = LLMSelector.get_client_config("bid_section_generate")
        client = AsyncOpenAI(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"] or None,
        )
        response = await client.chat.completions.create(
            model=cfg["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=4096,
        )
        result_text = response.choices[0].message.content or ""
        return ApiResponse(data={
            "original": body.original_text,
            "rewritten": result_text,
            "instruction": body.instruction,
            "model": cfg["model"],
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 重写失败: {str(e)}")


# ========== 风险报告 ==========

@router.post("/{project_id}/risk-report", response_model=ApiResponse)
async def generate_risk_report(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """生成投标风险报告（致命/严重/建议三级告警）"""
    svc = RiskReportService(session)
    try:
        report = await svc.generate_report(project_id, tenant_id)
        return ApiResponse(data=report)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风险报告生成失败: {str(e)}")


# ========== 评分覆盖率报告 ==========

@router.get("/{project_id}/coverage-report", response_model=ApiResponse)
async def get_coverage_report(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取评分点覆盖率报告 — 热力图数据

    返回各评分项对各章节的覆盖度矩阵，未覆盖项附带补充建议。
    """
    from app.services.bid_project_service import BidProjectService
    from app.services.generation.polish_pipeline import PolishResult
    from app.services.generation.reviewer import review_scoring_coverage

    svc = BidProjectService(session)
    project = await svc.get_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not project.chapters:
        raise HTTPException(status_code=400, detail="项目尚无章节，请先初始化")

    # 转换 BidChapter → PolishResult（reviewer 输入格式）
    chapters = [
        PolishResult(
            chapter_no=ch.chapter_no,
            title=ch.title,
            content=ch.content or "",
            changes_summary="",
            rounds_applied=0,
        )
        for ch in project.chapters
        if ch.content  # 跳过空章节
    ]

    if not chapters:
        raise HTTPException(status_code=400, detail="所有章节内容为空，请先生成")

    # 收集评分类需求
    scoring_reqs = [
        {
            "id": r.id,
            "content": r.content,
            "max_score": r.max_score,
        }
        for r in (project.requirements or [])
        if r.category == "scoring"
    ]

    # 运行覆盖率校验（关键词模式，快速响应）
    report = await review_scoring_coverage(chapters, scoring_reqs, threshold=0.6)

    # 构建热力图矩阵数据
    chapter_list = [{"chapter_no": ch.chapter_no, "title": ch.title} for ch in chapters]

    items = []
    for item in report.scoring_items:
        entry = {
            "requirement_id": item.requirement_id,
            "requirement_text": item.requirement_text,
            "max_score": item.max_score,
            "coverage_score": item.coverage_score,
            "covered_in": item.covered_in,
            "gap_note": item.gap_note,
            "remediation": None,
        }
        if item.remediation:
            entry["remediation"] = {
                "target_chapter": item.remediation.target_chapter,
                "target_title": item.remediation.target_title,
                "action": item.remediation.action,
                "priority": item.remediation.priority,
            }
        items.append(entry)

    return ApiResponse(data={
        "overall_coverage": report.overall_coverage,
        "total_items": len(report.scoring_items),
        "uncovered_count": len(report.uncovered_items),
        "chapters": chapter_list,
        "items": items,
    })


# ========== 反 AI 检测 ==========

@router.get("/{project_id}/ai-detection/{chapter_id}", response_model=ApiResponse)
async def detect_ai_chapter(
    project_id: int,
    chapter_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """检测单个章节的 AI 生成痕迹

    返回综合风险分（0~100）、五维度明细和修改建议。
    """
    from app.services.ai_detection_service import detect_ai_text

    svc = BidProjectService(session)
    project = await svc.get_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    chapter = next((ch for ch in project.chapters if ch.id == chapter_id), None)
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    if not chapter.content:
        raise HTTPException(status_code=400, detail="章节内容为空")

    report = detect_ai_text(chapter.content)

    return ApiResponse(data={
        "chapter_no": chapter.chapter_no,
        "title": chapter.title,
        "overall_score": report.overall_score,
        "risk_level": report.risk_level,
        "summary": report.summary,
        "dimensions": [
            {
                "name": d.name,
                "score": d.score,
                "detail": d.detail,
                "suggestion": d.suggestion,
            }
            for d in report.dimensions
        ],
    })


@router.get("/{project_id}/ai-detection", response_model=ApiResponse)
async def detect_ai_all_chapters(
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """批量检测所有章节的 AI 生成痕迹"""
    from app.services.ai_detection_service import detect_ai_text

    svc = BidProjectService(session)
    project = await svc.get_project(project_id, tenant_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    results = []
    total_score = 0.0
    count = 0

    for ch in project.chapters:
        if not ch.content:
            continue
        report = detect_ai_text(ch.content)
        results.append({
            "chapter_id": ch.id,
            "chapter_no": ch.chapter_no,
            "title": ch.title,
            "overall_score": report.overall_score,
            "risk_level": report.risk_level,
            "summary": report.summary,
        })
        total_score += report.overall_score
        count += 1

    avg_score = round(total_score / count, 1) if count > 0 else 0

    return ApiResponse(data={
        "project_avg_score": avg_score,
        "project_risk_level": "high" if avg_score >= 60 else "medium" if avg_score >= 35 else "low",
        "chapters": results,
    })
