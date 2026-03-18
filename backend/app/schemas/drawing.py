"""
图纸管理 Pydantic V2 Schema

所有 API 入参/出参统一通过 Pydantic 校验。
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ========== DrawingTemplate ==========

class DrawingCreate(BaseModel):
    """上传图纸时附带的元信息（文件通过 UploadFile 单独传）"""
    name: str
    category: str  # section/support/layout/schedule/safety/measure
    description: Optional[str] = None


class DrawingUpdate(BaseModel):
    """更新图纸元信息"""
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_current: Optional[bool] = None


class DrawingOut(BaseModel):
    """图纸输出模型"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    description: Optional[str] = None
    file_url: str
    file_format: Optional[str] = None
    file_size: Optional[int] = None
    version: int
    is_current: bool
    tenant_id: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ========== DrawingBinding ==========

class DrawingBindingCreate(BaseModel):
    """添加图纸-条件绑定"""
    condition_field: str  # rock_class / section_form / roadway_type / ...
    condition_value: str


class DrawingBindingOut(BaseModel):
    """绑定关系输出"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    drawing_id: int
    condition_field: str
    condition_value: str
    created_at: Optional[datetime] = None


# ========== 匹配请求 ==========

class DrawingMatchRequest(BaseModel):
    """根据项目参数匹配图纸"""
    rock_class: Optional[str] = None
    section_form: Optional[str] = None
    roadway_type: Optional[str] = None
    excavation_type: Optional[str] = None
    category: Optional[str] = None  # 可选：只匹配特定分类
