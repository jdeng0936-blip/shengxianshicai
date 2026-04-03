"""
企业管理 API 路由 — Enterprise CRUD
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse
from app.schemas.enterprise import EnterpriseCreate, EnterpriseUpdate, EnterpriseOut
from app.services.enterprise_service import EnterpriseService

router = APIRouter(prefix="/enterprises", tags=["企业管理"])


@router.get("", response_model=ApiResponse[list[EnterpriseOut]])
async def list_enterprises(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取当前租户的企业列表"""
    svc = EnterpriseService(session)
    items = await svc.list_enterprises(tenant_id)
    return ApiResponse(data=[EnterpriseOut.model_validate(e) for e in items])


@router.get("/{enterprise_id}", response_model=ApiResponse[EnterpriseOut])
async def get_enterprise(
    enterprise_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取企业详情（含资质和图片）"""
    svc = EnterpriseService(session)
    enterprise = await svc.get_enterprise(enterprise_id, tenant_id)
    if not enterprise:
        raise HTTPException(status_code=404, detail="企业不存在")
    return ApiResponse(data=EnterpriseOut.model_validate(enterprise))


@router.post("", response_model=ApiResponse[EnterpriseOut])
async def create_enterprise(
    body: EnterpriseCreate,
    tenant_id: int = Depends(get_tenant_id),
    payload: dict = Depends(get_current_user_payload),
    session: AsyncSession = Depends(get_async_session),
):
    """创建企业"""
    user_id = int(payload.get("sub", 0))
    svc = EnterpriseService(session)
    enterprise = await svc.create_enterprise(body, tenant_id, user_id)
    return ApiResponse(data=EnterpriseOut.model_validate(enterprise))


@router.put("/{enterprise_id}", response_model=ApiResponse[EnterpriseOut])
async def update_enterprise(
    enterprise_id: int,
    body: EnterpriseUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """更新企业信息"""
    svc = EnterpriseService(session)
    enterprise = await svc.update_enterprise(enterprise_id, tenant_id, body)
    if not enterprise:
        raise HTTPException(status_code=404, detail="企业不存在")
    return ApiResponse(data=EnterpriseOut.model_validate(enterprise))


@router.delete("/{enterprise_id}", response_model=ApiResponse)
async def delete_enterprise(
    enterprise_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除企业（级联删除资质和图片）"""
    svc = EnterpriseService(session)
    ok = await svc.delete_enterprise(enterprise_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="企业不存在")
    return ApiResponse(data={"deleted": True})


@router.get("/{enterprise_id}/readiness", response_model=ApiResponse)
async def check_readiness(
    enterprise_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """检查企业资料完整度（投标准备度评估）"""
    from app.services.readiness_check_service import ReadinessCheckService
    svc = ReadinessCheckService(session)
    try:
        result = await svc.check(enterprise_id, tenant_id)
        return ApiResponse(data=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ========== 企业能力画像 ==========

@router.get("/{enterprise_id}/profile", response_model=ApiResponse)
async def get_enterprise_profile(
    enterprise_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """企业能力画像 — 五维雷达图谱（硬件/合规/服务/文档/竞争）"""
    from app.services.capability_profile import CapabilityProfileService
    svc = CapabilityProfileService(session)
    try:
        profile = await svc.build_profile(enterprise_id, tenant_id)
        return ApiResponse(data=profile.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{enterprise_id}/match/{project_id}", response_model=ApiResponse)
async def match_enterprise_project(
    enterprise_id: int,
    project_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """企业能力 vs 招标要求匹配度评分"""
    from app.services.capability_profile import CapabilityProfileService
    svc = CapabilityProfileService(session)
    try:
        result = await svc.match_score(enterprise_id, project_id, tenant_id)
        return ApiResponse(data={
            "enterprise_id": result.enterprise_id,
            "project_id": result.project_id,
            "match_score": result.match_score,
            "strengths": result.strengths,
            "weaknesses": result.weaknesses,
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
