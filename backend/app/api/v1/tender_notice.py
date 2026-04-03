"""
商机漏斗 API 路由 — TenderNotice CRUD + 抓取分析 + 转化投标项目
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.schemas.tender_notice import (
    TenderNoticeCreate, TenderNoticeUpdate,
    TenderNoticeOut, TenderNoticeListOut, TenderNoticeStatsOut,
    TenderNoticeFetchRequest,
)
from app.services.tender_notice_service import TenderNoticeService
from app.services.tender_aggregator_service import TenderAggregatorService

router = APIRouter(prefix="/tender-notices", tags=["商机漏斗"])


# ========== 统计（放在 /{id} 之前避免路径冲突） ==========

@router.get("/stats", response_model=ApiResponse[TenderNoticeStatsOut])
async def get_stats(
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """商机统计面板"""
    svc = TenderNoticeService(session)
    stats = await svc.get_stats(tenant_id)
    return ApiResponse(data=stats)


@router.get("/regions", response_model=ApiResponse)
async def get_regions():
    """获取可选的抓取地区列表"""
    regions = TenderAggregatorService.get_available_regions()
    return ApiResponse(data=regions)


@router.get("/platforms", response_model=ApiResponse)
async def get_platforms():
    """获取可用的抓取平台列表"""
    platforms = TenderAggregatorService.get_available_platforms()
    return ApiResponse(data=platforms)


from pydantic import BaseModel as _PydanticBase, Field as _Field


class PasteNoticeRequest(_PydanticBase):
    raw_text: str = _Field(min_length=30, description="公告原文（从任意平台复制）")
    enterprise_id: int
    source_url: str | None = None


@router.post("/parse-text", response_model=ApiResponse[TenderNoticeOut])
async def parse_pasted_text(
    body: PasteNoticeRequest,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """AI 智能粘贴解析 — 从公告原文提取结构化商机信息"""
    user_id = int(payload.get("sub", 0))
    agg = TenderAggregatorService(session)
    try:
        notice = await agg.parse_raw_text(
            body.raw_text, tenant_id, body.enterprise_id, user_id, body.source_url,
        )
        return ApiResponse(data=TenderNoticeOut.model_validate(notice))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/crawl-all", response_model=ApiResponse)
async def crawl_all_platforms(
    body: TenderNoticeFetchRequest,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """多平台轮询抓取 + 自动 AI 分析匹配度"""
    user_id = int(payload.get("sub", 0))
    agg = TenderAggregatorService(session)

    # 1. 抓取
    result = await agg.crawl_all_platforms(
        tenant_id, body.enterprise_id, user_id, body.region, body.keywords,
    )

    # 2. 自动分析所有新入库的待分析商机
    analyzed_count = 0
    try:
        analyzed = await agg.batch_analyze(tenant_id, body.enterprise_id, user_id)
        analyzed_count = len(analyzed)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"批量分析失败: {e}")

    result["analyzed"] = analyzed_count
    return ApiResponse(data=result)


# ========== CRUD ==========

@router.get("", response_model=ApiResponse)
async def list_notices(
    status: Optional[str] = Query(None),
    match_level: Optional[str] = Query(None),
    page: int = 1,
    page_size: int = 20,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """商机列表（分页+筛选）"""
    svc = TenderNoticeService(session)
    items, total = await svc.list_notices(tenant_id, status, match_level, page, page_size)
    return ApiResponse(data={
        "items": [TenderNoticeListOut.model_validate(n) for n in items],
        "total": total,
        "page": page,
    })


@router.get("/{notice_id}", response_model=ApiResponse[TenderNoticeOut])
async def get_notice(
    notice_id: int,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """商机详情（含 AI 分析结果）"""
    svc = TenderNoticeService(session)
    notice = await svc.get_notice(notice_id, tenant_id)
    if not notice:
        raise HTTPException(status_code=404, detail="商机不存在")
    return ApiResponse(data=TenderNoticeOut.model_validate(notice))


@router.post("", response_model=ApiResponse[TenderNoticeOut])
async def create_notice(
    body: TenderNoticeCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """手动创建商机"""
    user_id = int(payload.get("sub", 0))
    svc = TenderNoticeService(session)
    notice = await svc.create_notice(body, tenant_id, user_id)
    return ApiResponse(data=TenderNoticeOut.model_validate(notice))


@router.put("/{notice_id}", response_model=ApiResponse[TenderNoticeOut])
async def update_notice(
    notice_id: int,
    body: TenderNoticeUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """更新商机"""
    svc = TenderNoticeService(session)
    notice = await svc.update_notice(notice_id, tenant_id, body)
    if not notice:
        raise HTTPException(status_code=404, detail="商机不存在")
    return ApiResponse(data=TenderNoticeOut.model_validate(notice))


@router.delete("/{notice_id}", response_model=ApiResponse)
async def delete_notice(
    notice_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除商机"""
    svc = TenderNoticeService(session)
    ok = await svc.delete_notice(notice_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="商机不存在")
    return ApiResponse(data={"deleted": True})


@router.post("/batch-delete", response_model=ApiResponse)
async def batch_delete_notices(
    body: dict,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """批量删除商机"""
    notice_ids = body.get("notice_ids", [])
    if not notice_ids:
        raise HTTPException(status_code=400, detail="请选择要删除的商机")
    svc = TenderNoticeService(session)
    deleted = 0
    for nid in notice_ids:
        ok = await svc.delete_notice(nid, tenant_id)
        if ok:
            deleted += 1
    return ApiResponse(data={"deleted": deleted, "total": len(notice_ids)})


# ========== 核心业务：抓取 + 分析 + 转化 ==========

@router.post("/fetch", response_model=ApiResponse)
async def fetch_and_analyze(
    body: TenderNoticeFetchRequest,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """抓取商机并自动 AI 分析匹配度"""
    user_id = int(payload.get("sub", 0))
    agg = TenderAggregatorService(session)

    # 1. 抓取
    notices = await agg.fetch_notices(
        tenant_id, body.enterprise_id, user_id,
        body.region, body.keywords, body.budget_min, body.budget_max,
    )

    # 2. 逐条分析
    analyzed = []
    for n in notices:
        notice_id = getattr(n, "id", n)  # 兼容对象和字符串/整数 ID
        try:
            result = await agg.analyze_notice(notice_id, tenant_id, body.enterprise_id)
            analyzed.append(TenderNoticeListOut.model_validate(result))
        except Exception as e:
            import traceback
            logger.error(f"fetch_and_analyze 调用 analyze_notice({notice_id}) 异常: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            if hasattr(n, "__dict__"):
                analyzed.append(TenderNoticeListOut.model_validate(n))
            # 非对象类型跳过，避免二次报错

    return ApiResponse(data={
        "fetched": len(notices),
        "analyzed": len(analyzed),
        "items": analyzed,
    })


@router.post("/{notice_id}/analyze", response_model=ApiResponse[TenderNoticeOut])
async def analyze_notice(
    notice_id: int,
    enterprise_id: int = Query(..., description="匹配分析的目标企业ID"),
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """对单条商机执行/重新执行 AI 匹配分析"""
    agg = TenderAggregatorService(session)
    try:
        notice = await agg.analyze_notice(notice_id, tenant_id, enterprise_id)
        return ApiResponse(data=TenderNoticeOut.model_validate(notice))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{notice_id}/dismiss", response_model=ApiResponse)
async def dismiss_notice(
    notice_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """忽略此商机"""
    svc = TenderNoticeService(session)
    notice = await svc.get_notice(notice_id, tenant_id)
    if not notice:
        raise HTTPException(status_code=404, detail="商机不存在")
    notice.status = "dismissed"
    await session.commit()
    return ApiResponse(data={"dismissed": True})


@router.post("/{notice_id}/convert", response_model=ApiResponse)
async def convert_to_project(
    notice_id: int,
    enterprise_id: int = Query(..., description="关联的投标企业ID"),
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """将商机转化为投标项目"""
    user_id = int(payload.get("sub", 0))
    agg = TenderAggregatorService(session)
    try:
        project = await agg.convert_to_project(notice_id, tenant_id, enterprise_id, user_id)
        return ApiResponse(data={
            "project_id": project.id,
            "project_name": project.project_name,
            "message": "商机已成功转化为投标项目",
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
