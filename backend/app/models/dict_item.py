"""
数据字典模型 — 通用键值对

用于管理业务下拉框选项（客户类型、招标方式、食材分类等）。
"""
from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, AuditMixin


class SysDictItem(AuditMixin, Base):
    """数据字典项"""
    __tablename__ = "sys_dict_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dict_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="字典类型(customer_type/tender_type/food_category/delivery_method/...)"
    )
    dict_key: Mapped[str] = mapped_column(String(50), nullable=False, comment="字典键")
    dict_value: Mapped[str] = mapped_column(String(200), nullable=False, comment="字典值（显示文本）")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序序号")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
