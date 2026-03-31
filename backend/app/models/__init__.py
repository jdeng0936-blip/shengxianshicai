"""
鲜标智投 — 数据模型统一导出

所有 SQLAlchemy 模型在此注册，确保 Alembic 能正确发现所有表。
"""
# 基础
from app.models.base import Base, AuditMixin  # noqa: F401

# 用户与权限（直接复用）
from app.models.user import SysUser, SysRole  # noqa: F401

# 核心业务模型（投标）
from app.models.enterprise import Enterprise  # noqa: F401
from app.models.bid_project import BidProject, TenderRequirement, BidChapter  # noqa: F401
from app.models.quotation import QuotationSheet, QuotationItem  # noqa: F401
from app.models.credential import Credential  # noqa: F401
from app.models.image_asset import ImageAsset  # noqa: F401

# 文档生成
from app.models.document import GeneratedDoc, DocTemplate, ChapterSnippet  # noqa: F401

# 知识库
from app.models.standard import StdDocument, StdClause, BidCase  # noqa: F401

# AI 对话
from app.models.chat import ChatSession, ChatMessageRecord  # noqa: F401

# 数据飞轮
from app.models.feedback import FeedbackLog  # noqa: F401

# 计费
from app.models.billing import UserQuota, UsageLog  # noqa: F401

# 系统
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.dict_item import SysDictItem  # noqa: F401
