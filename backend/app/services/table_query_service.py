"""
结构化参数查表服务 — L2 精确查询

功能:
  1. 根据围岩级别+断面形式 → 查支护参数推荐表
  2. 根据瓦斯等级+巷道类型 → 查通风标准表
  3. 根据掘进方式 → 查设备配置推荐表

设计:
  - 使用内存字典存储标准表数据（后续可迁移到 DB）
  - 返回精确匹配结果，无模糊搜索
  - 供 RAG 融合检索器和 AI Router 调用
"""
from typing import Optional


# ========== 支护参数推荐表 ==========
# key: (围岩级别, 断面形式) → 推荐参数
SUPPORT_TABLE: dict[tuple[str, str], dict] = {
    ("I", "矩形"): {
        "bolt_length": 1.8, "bolt_diameter": 18, "bolt_spacing": 1200,
        "bolt_row_spacing": 1200, "cable_count": 0, "cable_strength": 0,
        "remark": "I 类围岩稳定性好，一般不需锚索支护",
    },
    ("I", "拱形"): {
        "bolt_length": 1.8, "bolt_diameter": 18, "bolt_spacing": 1200,
        "bolt_row_spacing": 1200, "cable_count": 0, "cable_strength": 0,
        "remark": "I 类围岩稳定性好，拱形断面可仅喷浆",
    },
    ("II", "矩形"): {
        "bolt_length": 2.0, "bolt_diameter": 20, "bolt_spacing": 1000,
        "bolt_row_spacing": 1000, "cable_count": 0, "cable_strength": 0,
        "remark": "II 类围岩一般稳定，锚杆+钢筋网支护",
    },
    ("II", "拱形"): {
        "bolt_length": 2.0, "bolt_diameter": 20, "bolt_spacing": 1000,
        "bolt_row_spacing": 1000, "cable_count": 2, "cable_strength": 260,
        "remark": "II 类围岩拱形断面，建议配 2 根锚索",
    },
    ("III", "矩形"): {
        "bolt_length": 2.4, "bolt_diameter": 22, "bolt_spacing": 800,
        "bolt_row_spacing": 800, "cable_count": 3, "cable_strength": 260,
        "remark": "III 类围岩需加密锚杆，配 3 根锚索",
    },
    ("III", "拱形"): {
        "bolt_length": 2.4, "bolt_diameter": 22, "bolt_spacing": 800,
        "bolt_row_spacing": 800, "cable_count": 3, "cable_strength": 260,
        "remark": "III 类围岩拱形断面标准支护方案",
    },
    ("IV", "矩形"): {
        "bolt_length": 2.5, "bolt_diameter": 22, "bolt_spacing": 700,
        "bolt_row_spacing": 700, "cable_count": 4, "cable_strength": 300,
        "remark": "IV 类围岩不稳定，必须加密锚杆+锚索+钢带联合支护",
    },
    ("IV", "拱形"): {
        "bolt_length": 2.5, "bolt_diameter": 22, "bolt_spacing": 700,
        "bolt_row_spacing": 700, "cable_count": 5, "cable_strength": 300,
        "remark": "IV 类围岩拱形断面，锚杆+锚索+U 型钢拱架联合支护",
    },
    ("V", "矩形"): {
        "bolt_length": 2.8, "bolt_diameter": 22, "bolt_spacing": 600,
        "bolt_row_spacing": 600, "cable_count": 6, "cable_strength": 300,
        "remark": "V 类围岩极不稳定，必须全断面锚网索喷+钢拱架",
    },
    ("V", "拱形"): {
        "bolt_length": 2.8, "bolt_diameter": 22, "bolt_spacing": 600,
        "bolt_row_spacing": 600, "cable_count": 6, "cable_strength": 300,
        "remark": "V 类围岩极不稳定，全断面封闭支护",
    },
}

# ========== 通风标准表 ==========
# key: (瓦斯等级, 巷道类型) → 标准参数
VENT_TABLE: dict[tuple[str, str], dict] = {
    ("低瓦斯", "煤巷"): {
        "min_wind_speed": 0.25, "max_wind_speed": 4.0,
        "k_gas": 1.0, "dilution_factor": 100,
        "remark": "低瓦斯煤巷，按人数法和瓦斯涌出量法取较大值",
    },
    ("低瓦斯", "岩巷"): {
        "min_wind_speed": 0.15, "max_wind_speed": 4.0,
        "k_gas": 1.0, "dilution_factor": 100,
        "remark": "低瓦斯岩巷，风速要求较低",
    },
    ("高瓦斯", "煤巷"): {
        "min_wind_speed": 0.25, "max_wind_speed": 4.0,
        "k_gas": 1.5, "dilution_factor": 150,
        "remark": "高瓦斯煤巷，风量系数提升至 1.5",
    },
    ("高瓦斯", "岩巷"): {
        "min_wind_speed": 0.25, "max_wind_speed": 4.0,
        "k_gas": 1.2, "dilution_factor": 120,
        "remark": "高瓦斯岩巷，风量系数 1.2",
    },
    ("突出", "煤巷"): {
        "min_wind_speed": 0.25, "max_wind_speed": 4.0,
        "k_gas": 2.0, "dilution_factor": 200,
        "remark": "突出矿井煤巷，必须独立通风系统，风量系数 2.0",
    },
    ("突出", "岩巷"): {
        "min_wind_speed": 0.25, "max_wind_speed": 4.0,
        "k_gas": 1.5, "dilution_factor": 150,
        "remark": "突出矿井岩巷，参照高瓦斯标准",
    },
}

# ========== 设备配置推荐表 ==========
# key: 掘进方式 → 推荐设备
EQUIPMENT_TABLE: dict[str, dict] = {
    "钻爆法": {
        "drilling": "YT-28 气腿式凿岩机 × 4 台",
        "loading": "ZMC-30 型侧卸式装载机",
        "transport": "SGW-40T 型刮板输送机 + 皮带转载",
        "ventilation": "FBD-6.0/2×30 型对旋局扇",
        "dust_control": "SCF-6 型湿式除尘风机",
        "remark": "适用于中等硬度以上岩层，循环进尺 1.6-2.4m",
    },
    "综掘": {
        "drilling": "EBZ-200 型悬臂式掘进机",
        "loading": "机载转运（掘进机自带）",
        "transport": "DSJ-80/40/2×55 型胶带输送机",
        "ventilation": "FBD-8.0/2×55 型对旋局扇",
        "dust_control": "KCS-410D 型除尘风机",
        "remark": "适用于 f≤8 的中等及以下硬度煤岩，截割深度 0.6-0.8m",
    },
}


class TableQueryService:
    """结构化参数查表服务（L2 精确查询层）"""

    @staticmethod
    def query_support(rock_class: str, section_form: str = "拱形") -> Optional[dict]:
        """查支护参数推荐表"""
        # 梯形归并到矩形
        if section_form == "梯形":
            section_form = "矩形"
        key = (rock_class, section_form)
        result = SUPPORT_TABLE.get(key)
        if result:
            return {
                "source": "结构化参数表",
                "table": "支护参数推荐表",
                "query": f"围岩级别={rock_class}, 断面形式={section_form}",
                **result,
            }
        return None

    @staticmethod
    def query_ventilation(gas_level: str, tunnel_type: str = "煤巷") -> Optional[dict]:
        """查通风标准表"""
        key = (gas_level, tunnel_type)
        result = VENT_TABLE.get(key)
        if result:
            return {
                "source": "结构化参数表",
                "table": "通风标准表",
                "query": f"瓦斯等级={gas_level}, 巷道类型={tunnel_type}",
                **result,
            }
        return None

    @staticmethod
    def query_equipment(dig_method: str) -> Optional[dict]:
        """查设备配置推荐表"""
        result = EQUIPMENT_TABLE.get(dig_method)
        if result:
            return {
                "source": "结构化参数表",
                "table": "设备配置推荐表",
                "query": f"掘进方式={dig_method}",
                **result,
            }
        return None

    @classmethod
    def query(cls, table_name: str, **kwargs) -> Optional[dict]:
        """统一查询入口"""
        if table_name == "支护参数":
            return cls.query_support(
                kwargs.get("rock_class", "III"),
                kwargs.get("section_form", "拱形"),
            )
        elif table_name == "通风标准":
            return cls.query_ventilation(
                kwargs.get("gas_level", "低瓦斯"),
                kwargs.get("tunnel_type", "煤巷"),
            )
        elif table_name == "设备配置":
            return cls.query_equipment(
                kwargs.get("dig_method", "钻爆法"),
            )
        return None
