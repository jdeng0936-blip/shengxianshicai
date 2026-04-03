"""
投标章节模板引擎 — 定义标准投标文件章节结构

按 customer_type 选择不同侧重的模板，
并将招标评分标准映射到对应章节。
"""
from typing import Optional


# 标准投标文件章节结构（生鲜食材配送）
STANDARD_CHAPTERS = [
    {
        "chapter_no": "第一章",
        "title": "投标函及法定代表人授权书",
        "source": "template",
        "keywords": ["投标函", "授权书", "承诺"],
    },
    {
        "chapter_no": "第二章",
        "title": "企业简介及资格证明文件",
        "source": "credential",
        "keywords": ["营业执照", "食品经营许可", "资质", "资格", "证书", "信用"],
    },
    {
        "chapter_no": "第三章",
        "title": "食材采购与质量保障方案",
        "source": "ai",
        "keywords": ["采购", "质量", "溯源", "检测", "农残", "食品安全", "留样", "供应商"],
    },
    {
        "chapter_no": "第四章",
        "title": "仓储管理与冷链配送方案",
        "source": "ai",
        "keywords": ["仓储", "冷链", "配送", "冷库", "温控", "车辆", "GPS", "运输"],
    },
    {
        "chapter_no": "第五章",
        "title": "服务方案与应急保障",
        "source": "ai",
        "keywords": ["服务", "应急", "投诉", "售后", "响应", "替换", "保障", "节假日"],
    },
    {
        "chapter_no": "第六章",
        "title": "人员配置与培训方案",
        "source": "ai",
        "keywords": ["人员", "团队", "健康证", "培训", "考核", "厨师", "营养师", "配送员"],
    },
    {
        "chapter_no": "第七章",
        "title": "质量管理体系与食品安全制度",
        "source": "ai",
        "keywords": ["HACCP", "ISO", "管理体系", "制度", "标准", "体系认证", "管理"],
    },
    {
        "chapter_no": "第八章",
        "title": "报价文件",
        "source": "template",
        "keywords": ["报价", "价格", "下浮率", "折扣", "单价", "金额"],
    },
    {
        "chapter_no": "第九章",
        "title": "业绩案例与荣誉证书",
        "source": "credential",
        "keywords": ["业绩", "案例", "中标", "合同", "客户", "荣誉", "奖项"],
    },
]

# 按客户类型的章节侧重描述
CUSTOMER_EMPHASIS: dict[str, dict[str, str]] = {
    "school": {
        "第三章": "重点突出校园食品安全管理、学生营养搭配、农残检测100%覆盖、食材溯源到田间地头",
        "第四章": "强调早间配送（6:00前送达）、温控全程监控、分餐配送能力",
        "第五章": "强调节假日供餐弹性、突发事件（如食物中毒）应急预案、家长开放日机制",
        "第六章": "强调营养师配置、食堂驻点人员管理、从业人员健康证管理",
    },
    "hospital": {
        "第三章": "强调特殊膳食配方（糖尿病餐、流质餐等）、药膳搭配能力",
        "第四章": "强调24小时供餐能力、病房送餐流程、餐具消毒标准",
        "第五章": "强调紧急加餐响应（30分钟内）、传染病期间隔离供餐方案",
        "第六章": "强调营养师持证（注册营养技师）、医院卫生培训",
    },
    "government": {
        "第三章": "强调采购透明度、价格公示机制、第三方检测报告",
        "第四章": "强调准时率承诺（≥99%）、配送车辆GPS实时监控平台开放",
        "第五章": "强调投诉响应机制（2小时内处理）、定期满意度调查",
        "第六章": "强调管理团队资历、政府食堂服务经验",
    },
    "enterprise": {
        "第三章": "强调品种丰富度、季节性菜品更新、员工口味调研",
        "第四章": "强调写字楼/园区配送便捷性、午餐高峰时段集中配送能力",
        "第五章": "强调定制化菜单服务、VIP接待餐供应能力",
        "第六章": "强调厨师团队资质、中式/西式菜品能力",
    },
    "canteen": {
        "第三章": "强调大批量采购议价能力、多品类一站式供应",
        "第四章": "强调区域配送中心覆盖半径、多点同时配送能力",
        "第五章": "强调IT系统对接能力（ERP/采购系统接口）",
        "第六章": "强调团队规模化管理经验、跨区域调配能力",
    },
}


# 报价类章节类型标识 — 匹配到则跳过 LLM，直接返回空表模板
QUOTATION_CHAPTER_TYPES = ["quotation", "price_table", "报价表", "报价单", "报价明细", "报价文件"]

# 报价章节空表模板
_QUOTATION_EMPTY_TABLE = """## 报价文件

> 本章节数据由报价引擎自动生成，不使用 AI 撰写。

| 序号 | 品类 | 品名 | 规格 | 单位 | 单价(元) | 备注 |
|------|------|------|------|------|----------|------|
| 1    |      |      |      |      |          |      |
| 2    |      |      |      |      |          |      |
| 3    |      |      |      |      |          |      |

*报价数据请在「报价管理」模块中填写，导出时将自动注入本章节。*
"""


def is_quotation_chapter(chapter_no: str, title: str) -> bool:
    """判断是否为报价类章节（匹配则走空表策略，不调用 LLM）"""
    title_lower = title.lower()
    for keyword in QUOTATION_CHAPTER_TYPES:
        if keyword in title_lower:
            return True
    # 第八章固定为报价文件
    if chapter_no == "第八章":
        return True
    return False


def get_quotation_template() -> str:
    """返回报价章节空表模板"""
    return _QUOTATION_EMPTY_TABLE


def get_chapter_templates(customer_type: Optional[str] = None) -> list[dict]:
    """获取标准章节模板列表，带客户类型侧重描述"""
    chapters = []
    for ch in STANDARD_CHAPTERS:
        chapter = {**ch}
        if customer_type and customer_type in CUSTOMER_EMPHASIS:
            emphasis = CUSTOMER_EMPHASIS[customer_type].get(ch["chapter_no"])
            if emphasis:
                chapter["emphasis"] = emphasis
        chapters.append(chapter)
    return chapters


def map_requirements_to_chapters(
    requirements: list[dict],
    customer_type: Optional[str] = None,
) -> dict[str, list[dict]]:
    """将招标评分标准映射到对应章节

    Args:
        requirements: TenderRequirement 列表 (dict with content, category, max_score, etc.)
        customer_type: 客户类型

    Returns:
        { "第三章": [req1, req2, ...], "第四章": [...], ... }
    """
    chapters = get_chapter_templates(customer_type)
    mapping: dict[str, list[dict]] = {ch["chapter_no"]: [] for ch in chapters}

    for req in requirements:
        content_lower = req.get("content", "").lower()
        best_match = None
        best_score = 0

        for ch in chapters:
            score = sum(1 for kw in ch["keywords"] if kw in content_lower)
            if score > best_score:
                best_score = score
                best_match = ch["chapter_no"]

        if best_match and best_score > 0:
            mapping[best_match].append(req)
        elif req.get("category") == "scoring":
            # 评分标准无法匹配的放到技术方案章节
            mapping["第三章"].append(req)

    return mapping


def build_chapter_outline(
    chapter_no: str,
    title: str,
    mapped_requirements: list[dict],
    customer_type: Optional[str] = None,
) -> str:
    """为单个章节生成大纲文本（供 LLM prompt 使用）"""
    lines = [f"{chapter_no} {title}"]

    # 客户类型侧重
    if customer_type and customer_type in CUSTOMER_EMPHASIS:
        emphasis = CUSTOMER_EMPHASIS[customer_type].get(chapter_no)
        if emphasis:
            lines.append(f"\n【客户类型侧重】{emphasis}")

    # 映射的评分标准
    if mapped_requirements:
        lines.append("\n【本章须覆盖的评分标准】")
        for i, req in enumerate(mapped_requirements, 1):
            score_info = ""
            if req.get("max_score"):
                score_info = f"（{req['max_score']}分）"
            lines.append(f"  {i}. {req.get('content', '')}{score_info}")

    return "\n".join(lines)
