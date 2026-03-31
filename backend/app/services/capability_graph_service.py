"""
企业能力图谱服务 — 从 Enterprise + Credential 构建结构化能力画像

用途：注入 LLM Prompt 做商机匹配分析
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.enterprise import Enterprise
from app.models.credential import Credential

# 15 种标准资质类型
STANDARD_CRED_TYPES = {
    "food_license": "食品经营许可证",
    "business_license": "营业执照",
    "haccp": "HACCP认证",
    "iso22000": "ISO22000认证",
    "sc": "SC认证",
    "animal_quarantine": "动物防疫合格证",
    "cold_chain_transport": "冷链运输资质",
    "health_certificate": "从业人员健康证",
    "liability_insurance": "公众责任险",
    "quality_inspection": "质量检验报告",
    "organic_cert": "有机认证",
    "green_food": "绿色食品认证",
    "performance": "业绩证明",
    "award": "荣誉证书",
    "other": "其他",
}


def _is_valid_credential(cred: Credential) -> bool:
    if cred.is_permanent:
        return True
    if not cred.expiry_date:
        return True
    try:
        expiry = datetime.strptime(cred.expiry_date, "%Y-%m-%d").date()
        return expiry >= date.today()
    except (ValueError, TypeError):
        return True


class CapabilityGraphService:
    """企业能力图谱构建"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def build_graph(self, enterprise_id: int, tenant_id: int) -> dict:
        """构建结构化能力画像 dict（可直接序列化为文本注入 Prompt）"""
        result = await self.session.execute(
            select(Enterprise)
            .options(selectinload(Enterprise.credentials))
            .where(Enterprise.id == enterprise_id, Enterprise.tenant_id == tenant_id)
        )
        ent = result.scalar_one_or_none()
        if not ent:
            return {"error": "企业不存在"}

        # 资质清单
        valid_creds = []
        expired_creds = []
        cred_types_held = set()
        for c in (ent.credentials or []):
            cred_types_held.add(c.cred_type)
            if _is_valid_credential(c):
                valid_creds.append({"type": c.cred_type, "name": c.cred_name, "expiry": c.expiry_date})
            else:
                expired_creds.append({"type": c.cred_type, "name": c.cred_name, "expiry": c.expiry_date})

        # 缺失的资质
        gaps = [
            STANDARD_CRED_TYPES[k]
            for k in ["food_license", "business_license", "haccp", "iso22000", "sc",
                       "cold_chain_transport", "health_certificate", "liability_insurance"]
            if k not in cred_types_held
        ]

        graph = {
            "enterprise_name": ent.name,
            "certifications": {
                "haccp": ent.haccp_certified,
                "iso22000": ent.iso22000_certified,
                "sc": ent.sc_certified,
                "food_license": bool(ent.food_license_no),
            },
            "cold_chain": {
                "cold_chain_vehicles": ent.cold_chain_vehicles or 0,
                "normal_vehicles": ent.normal_vehicles or 0,
                "warehouse_area_sqm": ent.warehouse_area,
                "cold_storage_area_sqm": ent.cold_storage_area,
                "cold_storage_temp": ent.cold_storage_temp,
            },
            "business_scale": {
                "employees": ent.employee_count,
                "annual_revenue": ent.annual_revenue,
                "service_customers": ent.service_customers,
                "registered_capital": ent.registered_capital,
            },
            "valid_credentials": valid_creds,
            "expired_credentials": expired_creds,
            "credential_gaps": gaps,
            "competitive_advantages": ent.competitive_advantages or "",
            "address": ent.address or "",
        }
        return graph

    def graph_to_text(self, graph: dict) -> str:
        """将能力图谱 dict 转为 Prompt 可读文本"""
        if "error" in graph:
            return "企业信息不可用"

        lines = [f"企业名称：{graph['enterprise_name']}"]

        certs = graph.get("certifications", {})
        cert_list = [k for k, v in certs.items() if v]
        lines.append(f"已通过认证：{', '.join(cert_list) if cert_list else '无'}")

        cc = graph.get("cold_chain", {})
        lines.append(f"冷链车辆：{cc.get('cold_chain_vehicles', 0)}辆，常温车辆：{cc.get('normal_vehicles', 0)}辆")
        if cc.get("warehouse_area_sqm"):
            lines.append(f"仓储面积：{cc['warehouse_area_sqm']}㎡")
        if cc.get("cold_storage_area_sqm"):
            lines.append(f"冷库面积：{cc['cold_storage_area_sqm']}㎡（{cc.get('cold_storage_temp', '未知')}）")

        bs = graph.get("business_scale", {})
        if bs.get("employees"):
            lines.append(f"员工人数：{bs['employees']}人")
        if bs.get("service_customers"):
            lines.append(f"服务客户数：{bs['service_customers']}家")
        if bs.get("annual_revenue"):
            lines.append(f"年营收：{bs['annual_revenue']}万元")

        valid = graph.get("valid_credentials", [])
        if valid:
            lines.append(f"有效资质（{len(valid)}项）：" + "、".join(c["name"] for c in valid))

        gaps = graph.get("credential_gaps", [])
        if gaps:
            lines.append(f"缺失资质：{'、'.join(gaps)}")

        if graph.get("competitive_advantages"):
            lines.append(f"核心优势：{graph['competitive_advantages']}")

        return "\n".join(lines)
