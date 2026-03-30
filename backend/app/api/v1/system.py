"""
系统管理 API 路由

覆盖用户管理、角色权限、操作日志、数据字典四个子模块。
所有接口强制 JWT 认证 + tenant_id 隔离。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.deps import get_current_user_payload, get_tenant_id
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.system import (
    UserCreate, UserUpdate, UserOut, PasswordReset,
    RoleCreate, RoleUpdate, RoleOut,
    AuditLogOut,
    DictItemCreate, DictItemUpdate, DictItemOut,
)
from app.services.system_service import (
    UserService, RoleService, AuditLogService, DictService,
)

router = APIRouter(prefix="/system", tags=["系统管理"])


# ==================== 用户管理 ====================

@router.get("/users", response_model=ApiResponse[PaginatedData[UserOut]])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    username: Optional[str] = Query(None, description="用户名模糊搜索"),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取用户列表"""
    svc = UserService(session)
    users, total = await svc.list_users(tenant_id, page, page_size, username)
    items = []
    for u in users:
        items.append(UserOut(
            id=u.id, username=u.username, real_name=u.real_name,
            role_id=u.role_id, role_name=u.role.name if u.role else None,
            is_active=u.is_active, tenant_id=u.tenant_id, created_at=u.created_at,
        ))
    return ApiResponse(data=PaginatedData(items=items, total=total, page=page, page_size=page_size))


@router.post("/users", response_model=ApiResponse[UserOut], status_code=201)
async def create_user(
    body: UserCreate,
    payload: dict = Depends(get_current_user_payload),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """新增用户"""
    svc = UserService(session)
    try:
        user = await svc.create_user(body, tenant_id, int(payload["sub"]))
        await session.commit()
        return ApiResponse(data=UserOut(
            id=user.id, username=user.username, real_name=user.real_name,
            role_id=user.role_id, role_name=user.role.name if user.role else None,
            is_active=user.is_active, tenant_id=user.tenant_id, created_at=user.created_at,
        ))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/users/{user_id}", response_model=ApiResponse[UserOut])
async def update_user(
    user_id: int,
    body: UserUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """编辑用户信息"""
    svc = UserService(session)
    user = await svc.update_user(user_id, tenant_id, body)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await session.commit()
    return ApiResponse(data=UserOut(
        id=user.id, username=user.username, real_name=user.real_name,
        role_id=user.role_id, role_name=user.role.name if user.role else None,
        is_active=user.is_active, tenant_id=user.tenant_id, created_at=user.created_at,
    ))


@router.put("/users/{user_id}/toggle", response_model=ApiResponse[UserOut])
async def toggle_user(
    user_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """启用/禁用用户"""
    svc = UserService(session)
    user = await svc.toggle_active(user_id, tenant_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    await session.commit()
    return ApiResponse(data=UserOut(
        id=user.id, username=user.username, real_name=user.real_name,
        role_id=user.role_id, role_name=user.role.name if user.role else None,
        is_active=user.is_active, tenant_id=user.tenant_id, created_at=user.created_at,
    ))


@router.put("/users/{user_id}/password", response_model=ApiResponse)
async def reset_password(
    user_id: int,
    body: PasswordReset,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """重置用户密码"""
    svc = UserService(session)
    ok = await svc.reset_password(user_id, tenant_id, body)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    await session.commit()
    return ApiResponse(message="密码重置成功")


# ==================== 角色管理 ====================

@router.get("/roles", response_model=ApiResponse[list[RoleOut]])
async def list_roles(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取角色列表"""
    svc = RoleService(session)
    roles = await svc.list_roles(tenant_id)
    return ApiResponse(data=[RoleOut.model_validate(r) for r in roles])


@router.post("/roles", response_model=ApiResponse[RoleOut], status_code=201)
async def create_role(
    body: RoleCreate,
    payload: dict = Depends(get_current_user_payload),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """新增角色"""
    svc = RoleService(session)
    role = await svc.create_role(body, tenant_id, int(payload["sub"]))
    await session.commit()
    return ApiResponse(data=RoleOut.model_validate(role))


@router.put("/roles/{role_id}", response_model=ApiResponse[RoleOut])
async def update_role(
    role_id: int,
    body: RoleUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """编辑角色"""
    svc = RoleService(session)
    role = await svc.update_role(role_id, tenant_id, body)
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    await session.commit()
    return ApiResponse(data=RoleOut.model_validate(role))


@router.delete("/roles/{role_id}", response_model=ApiResponse)
async def delete_role(
    role_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除角色"""
    svc = RoleService(session)
    ok = await svc.delete_role(role_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="角色不存在")
    await session.commit()
    return ApiResponse(message="删除成功")



# ==================== 操作日志 ====================

@router.get("/logs", response_model=ApiResponse[PaginatedData[AuditLogOut]])
async def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None, description="操作类型筛选"),
    resource: Optional[str] = Query(None, description="资源类型筛选"),
    username: Optional[str] = Query(None, description="操作人模糊搜索"),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取操作日志"""
    svc = AuditLogService(session)
    logs, total = await svc.list_logs(tenant_id, page, page_size, action, resource, username)
    return ApiResponse(data=PaginatedData(
        items=[AuditLogOut.model_validate(log) for log in logs],
        total=total, page=page, page_size=page_size,
    ))


# ==================== 数据字典 ====================

@router.get("/dicts", response_model=ApiResponse[list[DictItemOut]])
async def list_dicts(
    dict_type: Optional[str] = Query(None, description="字典类型筛选"),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取字典项列表"""
    svc = DictService(session)
    items = await svc.list_by_type(tenant_id, dict_type)
    return ApiResponse(data=[DictItemOut.model_validate(i) for i in items])


@router.get("/dicts/types", response_model=ApiResponse[list[str]])
async def list_dict_types(
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """获取所有字典类型"""
    svc = DictService(session)
    types = await svc.get_dict_types(tenant_id)
    return ApiResponse(data=types)


@router.post("/dicts", response_model=ApiResponse[DictItemOut], status_code=201)
async def create_dict(
    body: DictItemCreate,
    payload: dict = Depends(get_current_user_payload),
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """新增字典项"""
    svc = DictService(session)
    item = await svc.create_item(body, tenant_id, int(payload["sub"]))
    await session.commit()
    return ApiResponse(data=DictItemOut.model_validate(item))


@router.put("/dicts/{item_id}", response_model=ApiResponse[DictItemOut])
async def update_dict(
    item_id: int,
    body: DictItemUpdate,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """编辑字典项"""
    svc = DictService(session)
    item = await svc.update_item(item_id, tenant_id, body)
    if not item:
        raise HTTPException(status_code=404, detail="字典项不存在")
    await session.commit()
    return ApiResponse(data=DictItemOut.model_validate(item))


@router.delete("/dicts/{item_id}", response_model=ApiResponse)
async def delete_dict(
    item_id: int,
    tenant_id: int = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_async_session),
):
    """删除字典项"""
    svc = DictService(session)
    ok = await svc.delete_item(item_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="字典项不存在")
    await session.commit()
    return ApiResponse(message="删除成功")
