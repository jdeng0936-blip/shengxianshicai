"""
图纸管理模型 — DrawingTemplate + DrawingBinding

规范：所有业务表混入 AuditMixin（created_at, updated_at, created_by, tenant_id）
"""
from sqlalchemy import String, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, AuditMixin


class DrawingTemplate(AuditMixin, Base):
    """图纸模板"""
    __tablename__ = "drawing_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="图纸名称")
    category: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="分类(section/support/layout/schedule/safety/measure)",
    )
    description: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="图纸描述"
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False, comment="图纸文件存储路径")
    file_format: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="文件格式(dwg/pdf/png/jpg/svg)")
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="文件大小(字节)")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="版本号")
    is_current: Mapped[bool] = mapped_column(Integer, default=True, comment="是否当前有效版本")

    # 关联绑定关系
    bindings: Mapped[list["DrawingBinding"]] = relationship(
        "DrawingBinding", back_populates="drawing", cascade="all, delete-orphan"
    )


class DrawingBinding(AuditMixin, Base):
    """图纸-条件绑定关系

    将图纸绑定到特定的参数条件（如围岩级别、断面形式等），
    以便在参数匹配时自动推荐相关图纸。
    """
    __tablename__ = "drawing_binding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("drawing_template.id", ondelete="CASCADE"), nullable=False
    )
    condition_field: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="绑定字段(rock_class/section_form/roadway_type/...)"
    )
    condition_value: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="绑定值"
    )

    # 反向关联
    drawing: Mapped["DrawingTemplate"] = relationship(
        "DrawingTemplate", back_populates="bindings"
    )
