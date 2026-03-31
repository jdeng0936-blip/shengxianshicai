"""
商机公告 Schema — Pydantic V2
"""
import json
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


class TenderNoticeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    buyer_name: Optional[str] = None
    buyer_region: Optional[str] = None
    customer_type: Optional[str] = None
    tender_type: Optional[str] = None
    budget_amount: Optional[float] = None
    deadline: Optional[str] = None
    publish_date: Optional[str] = None
    delivery_scope: Optional[str] = None
    content_summary: Optional[str] = None
    source: str = "manual"
    source_url: Optional[str] = None


class TenderNoticeUpdate(BaseModel):
    title: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_region: Optional[str] = None
    customer_type: Optional[str] = None
    tender_type: Optional[str] = None
    budget_amount: Optional[float] = None
    deadline: Optional[str] = None
    delivery_scope: Optional[str] = None
    content_summary: Optional[str] = None
    status: Optional[str] = None
    enterprise_id: Optional[int] = None


class TenderNoticeListOut(BaseModel):
    id: int
    title: str
    buyer_name: Optional[str] = None
    buyer_region: Optional[str] = None
    customer_type: Optional[str] = None
    budget_amount: Optional[float] = None
    deadline: Optional[str] = None
    publish_date: Optional[str] = None
    match_score: Optional[float] = None
    match_level: Optional[str] = None
    status: str
    recommendation: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TenderNoticeOut(BaseModel):
    id: int
    tenant_id: int
    enterprise_id: Optional[int] = None
    source: str
    source_url: Optional[str] = None
    title: str
    buyer_name: Optional[str] = None
    buyer_region: Optional[str] = None
    customer_type: Optional[str] = None
    tender_type: Optional[str] = None
    budget_amount: Optional[float] = None
    deadline: Optional[str] = None
    publish_date: Optional[str] = None
    delivery_scope: Optional[str] = None
    content_summary: Optional[str] = None
    match_score: Optional[float] = None
    match_level: Optional[str] = None
    match_analysis: Optional[dict] = None
    capability_gaps: Optional[list] = None
    recommendation: Optional[str] = None
    status: str
    converted_project_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("match_analysis", mode="before")
    @classmethod
    def parse_match_analysis(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

    @field_validator("capability_gaps", mode="before")
    @classmethod
    def parse_capability_gaps(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v


class TenderNoticeStatsOut(BaseModel):
    total: int = 0
    new_count: int = 0
    recommended: int = 0
    risky: int = 0
    converted: int = 0
    avg_match_score: Optional[float] = None


class TenderNoticeFetchRequest(BaseModel):
    enterprise_id: int
    region: Optional[str] = None
    keywords: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
