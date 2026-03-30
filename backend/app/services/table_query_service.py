"""
生鲜投标结构化数据查询服务

提供行业标准参数表查询功能:
  1. 根据食材品类 → 查冷链温控标准
  2. 根据客户类型 → 查配送频次与合规要求

被 ai_router.py Tool Calling 调用。

注: MVP 阶段仅提供基础查表能力，后续将对接 ERP 实时数据。
"""
from typing import Optional


# ========== 冷链温控标准表 ==========
# 参考: GB/T 28577-2012, GB 31605-2020
COLD_CHAIN_STANDARDS: dict[str, dict] = {
    "蔬菜类": {
        "storage_temp": "0~5°C", "transport_temp": "0~10°C",
        "shelf_life_days": "3~7天", "humidity": "85~95%",
        "remark": "叶菜类需预冷处理，根茎类可适当放宽温度",
    },
    "肉类": {
        "storage_temp": "-18°C以下(冻品) / 0~4°C(鲜品)", "transport_temp": "-15°C以下(冻) / 0~4°C(鲜)",
        "shelf_life_days": "冻品12个月/鲜品3天", "humidity": "80~85%",
        "remark": "需提供动物检疫合格证明，注意交叉污染防控",
    },
    "水产类": {
        "storage_temp": "-18°C以下(冻品) / 0~4°C(鲜品)", "transport_temp": "-15°C(冻) / 0~5°C(鲜活)",
        "shelf_life_days": "冻品6个月/鲜品1~2天", "humidity": "85~90%",
        "remark": "鲜活水产需充氧运输，冰鲜品需加冰保温",
    },
    "蛋禽类": {
        "storage_temp": "0~5°C", "transport_temp": "0~10°C",
        "shelf_life_days": "鲜蛋30天/禽肉3天", "humidity": "80~85%",
        "remark": "蛋品需轻拿轻放，独立包装避免破损",
    },
    "干货类": {
        "storage_temp": "常温(≤25°C)", "transport_temp": "常温",
        "shelf_life_days": "6~12个月", "humidity": "<65%",
        "remark": "注意防潮防虫，原包装密封保存",
    },
    "调料类": {
        "storage_temp": "常温(≤25°C)", "transport_temp": "常温",
        "shelf_life_days": "按包装标注", "humidity": "<70%",
        "remark": "液态调料需防漏包装，粉状调料需防潮",
    },
}

# ========== 客户配送标准表 ==========
DELIVERY_STANDARDS: dict[str, dict] = {
    "学校食堂": {
        "delivery_freq": "每日配送", "morning_deadline": "6:30前到校",
        "quality_check": "每批次留样48小时",
        "cert_required": "食品经营许可证、从业人员健康证、送货单三联",
        "remark": "应符合《学校食品安全与营养健康管理规定》",
    },
    "机关单位": {
        "delivery_freq": "每日或隔日", "morning_deadline": "7:00前到达",
        "quality_check": "每批抽检，月度汇总报告",
        "cert_required": "食品经营许可证、检验检疫证明",
        "remark": "政府采购项目需注意合规流程",
    },
    "医院食堂": {
        "delivery_freq": "每日配送", "morning_deadline": "5:30前到达",
        "quality_check": "每批次检验报告+留样72小时",
        "cert_required": "食品经营许可证、车辆消毒记录、人员健康证",
        "remark": "特殊膳食需求较多，需配合营养科对接",
    },
    "企业食堂": {
        "delivery_freq": "按需(通常每日)", "morning_deadline": "7:00前到达",
        "quality_check": "按合同约定抽检",
        "cert_required": "食品经营许可证",
        "remark": "注意用量波动管理，节假日需提前沟通",
    },
}


class TableQueryService:
    """生鲜投标结构化查表服务"""

    @staticmethod
    def query_cold_chain(food_category: str) -> Optional[dict]:
        """根据食材品类查冷链温控标准"""
        data = COLD_CHAIN_STANDARDS.get(food_category)
        if data:
            return {
                "table": "冷链温控标准表",
                "query": f"食材品类={food_category}",
                **data,
            }
        return None

    @staticmethod
    def query_delivery(customer_type: str) -> Optional[dict]:
        """根据客户类型查配送标准"""
        data = DELIVERY_STANDARDS.get(customer_type)
        if data:
            return {
                "table": "客户配送标准表",
                "query": f"客户类型={customer_type}",
                **data,
            }
        return None

    @staticmethod
    def query(table_name: str, **kwargs) -> Optional[dict]:
        """统一查表入口 — 供 AI Tool Calling 调度"""
        if table_name in ("冷链温控", "冷链标准", "cold_chain"):
            return TableQueryService.query_cold_chain(
                kwargs.get("food_category", "蔬菜类"),
            )
        elif table_name in ("配送标准", "delivery"):
            return TableQueryService.query_delivery(
                kwargs.get("customer_type", "学校食堂"),
            )
        return None

    @staticmethod
    def list_tables() -> list[str]:
        """返回可查表的列表（供 LLM 工具描述使用）"""
        return ["冷链温控标准表", "客户配送标准表"]
