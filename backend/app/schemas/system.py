"""
系统管理 Pydantic V2 Schema

覆盖用户、角色、操作日志、数据字典四个子模块。
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ========== 用户管理 ==========

class UserCreate(BaseModel):
    """新增用户"""
    username: str
    password: str
    real_name: Optional[str] = None
    role_id: Optional[int] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    """编辑用户信息（不含密码）"""
    real_name: Optional[str] = None
    role_id: Optional[int] = None


class PasswordReset(BaseModel):
    """重置密码"""
    new_password: str


class UserOut(BaseModel):
    """用户输出"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    real_name: Optional[str] = None
    role_id: Optional[int] = None
    role_name: Optional[str] = None  # 手动填充
    is_active: bool
    tenant_id: int
    created_at: Optional[datetime] = None


# ========== 角色管理 ==========

class RoleCreate(BaseModel):
    """新增角色"""
    name: str
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    """编辑角色"""
    name: Optional[str] = None
    description: Optional[str] = None


class RoleOut(BaseModel):
    """角色输出"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None


# ========== 操作日志 ==========

class AuditLogOut(BaseModel):
    """操作日志输出（只读）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str
    action: str
    resource: str
    detail: Optional[str] = None
    ip_address: Optional[str] = None
    tenant_id: int
    created_at: Optional[datetime] = None


# ========== 数据字典 ==========

class DictItemCreate(BaseModel):
    """新增字典项"""
    dict_type: str
    dict_key: str
    dict_value: str
    sort_order: int = 0
    is_active: bool = True


class DictItemUpdate(BaseModel):
    """编辑字典项"""
    dict_key: Optional[str] = None
    dict_value: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class DictItemOut(BaseModel):
    """字典项输出"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    dict_type: str
    dict_key: str
    dict_value: str
    sort_order: int
    is_active: bool
    created_at: Optional[datetime] = None
