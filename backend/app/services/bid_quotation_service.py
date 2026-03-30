"""
报价单自动初始化服务 — 从招标要求中提取品类框架，生成预填报价单

流程:
  1. 读取招标要求中的评分标准/商务要求/技术要求
  2. 从关键词推断需要报价的食材品类
  3. 按品类预填常见食材品目（名称/规格/单位/参考价）
  4. 根据项目预算和下浮率推算参考单价
  5. 创建 QuotationSheet + QuotationItem

架构红线:
  - 报价数值仅作参考预填，最终定价由用户确认
  - 下浮率限制: QUOTATION_MIN_DISCOUNT ~ QUOTATION_MAX_DISCOUNT
"""
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.bid_project import BidProject
from app.models.quotation import QuotationSheet, QuotationItem
from app.services.bid_project_service import BidProjectService


# ---------- 六大品类预填食材库 ----------
# 每个品类提供 5-8 种高频食材作为初始框架
_DEFAULT_ITEMS: dict[str, list[dict]] = {
    "vegetable": [
        {"item_name": "大白菜", "spec": "一级", "unit": "kg", "market_ref_price": 2.5},
        {"item_name": "西红柿", "spec": "精品", "unit": "kg", "market_ref_price": 5.0},
        {"item_name": "黄瓜", "spec": "一级", "unit": "kg", "market_ref_price": 4.0},
        {"item_name": "土豆", "spec": "一级", "unit": "kg", "market_ref_price": 3.0},
        {"item_name": "青椒", "spec": "一级", "unit": "kg", "market_ref_price": 5.5},
        {"item_name": "胡萝卜", "spec": "一级", "unit": "kg", "market_ref_price": 3.5},
        {"item_name": "花菜", "spec": "一级", "unit": "kg", "market_ref_price": 5.0},
        {"item_name": "生菜", "spec": "精品", "unit": "kg", "market_ref_price": 6.0},
    ],
    "meat": [
        {"item_name": "猪五花肉", "spec": "鲜品", "unit": "kg", "market_ref_price": 28.0},
        {"item_name": "猪瘦肉", "spec": "鲜品", "unit": "kg", "market_ref_price": 30.0},
        {"item_name": "猪排骨", "spec": "鲜品", "unit": "kg", "market_ref_price": 35.0},
        {"item_name": "牛腩", "spec": "鲜品", "unit": "kg", "market_ref_price": 55.0},
        {"item_name": "鸡胸肉", "spec": "冷鲜", "unit": "kg", "market_ref_price": 18.0},
        {"item_name": "鸡翅中", "spec": "冷鲜", "unit": "kg", "market_ref_price": 22.0},
    ],
    "seafood": [
        {"item_name": "草鱼", "spec": "活鲜", "unit": "kg", "market_ref_price": 15.0},
        {"item_name": "鲈鱼", "spec": "活鲜", "unit": "kg", "market_ref_price": 25.0},
        {"item_name": "基围虾", "spec": "鲜活", "unit": "kg", "market_ref_price": 45.0},
        {"item_name": "带鱼段", "spec": "冷冻", "unit": "kg", "market_ref_price": 20.0},
        {"item_name": "墨鱼仔", "spec": "冷冻", "unit": "kg", "market_ref_price": 28.0},
    ],
    "egg_poultry": [
        {"item_name": "鸡蛋", "spec": "鲜品", "unit": "kg", "market_ref_price": 10.0},
        {"item_name": "鹌鹑蛋", "spec": "鲜品", "unit": "kg", "market_ref_price": 14.0},
        {"item_name": "白条鸡", "spec": "冷鲜", "unit": "kg", "market_ref_price": 16.0},
        {"item_name": "白条鸭", "spec": "冷鲜", "unit": "kg", "market_ref_price": 18.0},
    ],
    "dry_goods": [
        {"item_name": "大米", "spec": "一级", "unit": "kg", "market_ref_price": 5.0},
        {"item_name": "面粉", "spec": "特一粉", "unit": "kg", "market_ref_price": 4.5},
        {"item_name": "食用油", "spec": "一级大豆油", "unit": "L", "market_ref_price": 10.0},
        {"item_name": "腐竹", "spec": "干品", "unit": "kg", "market_ref_price": 15.0},
        {"item_name": "粉丝", "spec": "干品", "unit": "kg", "market_ref_price": 8.0},
        {"item_name": "木耳", "spec": "干品", "unit": "kg", "market_ref_price": 50.0},
    ],
    "condiment": [
        {"item_name": "食盐", "spec": "精制盐", "unit": "kg", "market_ref_price": 3.0},
        {"item_name": "酱油", "spec": "一级", "unit": "L", "market_ref_price": 8.0},
        {"item_name": "醋", "spec": "酿造食醋", "unit": "L", "market_ref_price": 6.0},
        {"item_name": "白砂糖", "spec": "一级", "unit": "kg", "market_ref_price": 7.0},
        {"item_name": "鸡精", "spec": "袋装", "unit": "kg", "market_ref_price": 15.0},
    ],
}

# 品类关键词匹配
_CATEGORY_KEYWORDS = {
    "vegetable": ["蔬菜", "青菜", "叶菜", "根茎"],
    "meat": ["肉类", "猪肉", "牛肉", "羊肉", "鲜肉"],
    "seafood": ["水产", "海鲜", "鱼类", "虾"],
    "egg_poultry": ["蛋", "禽", "鸡", "鸭"],
    "dry_goods": ["干货", "粮油", "大米", "面粉", "食用油"],
    "condiment": ["调料", "调味品", "佐料"],
}


class BidQuotationService:
    """报价单自动初始化服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def init_quotation(
        self,
        project_id: int,
        tenant_id: int,
        user_id: int,
        discount_rate: Optional[float] = None,
    ) -> QuotationSheet:
        """
        根据招标要求自动初始化报价单。

        逻辑:
          1. 从招标要求关键词推断需要的品类（默认全部六大品类）
          2. 预填常见食材品目 + 市场参考价
          3. 按下浮率计算投标单价
          4. 创建 QuotationSheet + QuotationItem

        Args:
            discount_rate: 下浮率（None 则使用默认中间值）

        Returns:
            创建的 QuotationSheet（含 items）
        """
        svc = BidProjectService(self.session)
        project = await svc.get_project(project_id, tenant_id)
        if not project:
            raise ValueError("投标项目不存在")

        # 确定下浮率
        if discount_rate is None:
            discount_rate = (settings.QUOTATION_MIN_DISCOUNT + settings.QUOTATION_MAX_DISCOUNT) / 2
        discount_rate = max(
            settings.QUOTATION_MIN_DISCOUNT,
            min(discount_rate, settings.QUOTATION_MAX_DISCOUNT),
        )

        # 推断需要报价的品类
        categories = self._detect_categories(project)

        # 自动递增版本号
        max_ver = await self.session.execute(
            select(func.coalesce(func.max(QuotationSheet.version), 0))
            .where(QuotationSheet.project_id == project_id)
        )
        next_version = (max_ver.scalar() or 0) + 1

        # 创建报价表
        sheet = QuotationSheet(
            project_id=project_id,
            version=next_version,
            discount_rate=discount_rate,
            budget_amount=project.budget_amount,
            pricing_method="discount_rate",
            remarks=f"根据招标要求自动初始化（下浮率 {discount_rate * 100:.1f}%）",
            tenant_id=tenant_id,
            created_by=user_id,
        )
        self.session.add(sheet)
        await self.session.flush()

        # 预填品目
        total = 0.0
        sort_idx = 0
        for cat in categories:
            items = _DEFAULT_ITEMS.get(cat, [])
            for item_data in items:
                ref_price = item_data["market_ref_price"]
                unit_price = round(ref_price * (1 - discount_rate), 2)
                item = QuotationItem(
                    sheet_id=sheet.id,
                    category=cat,
                    item_name=item_data["item_name"],
                    spec=item_data.get("spec"),
                    unit=item_data.get("unit"),
                    market_ref_price=ref_price,
                    unit_price=unit_price,
                    sort_order=sort_idx,
                    tenant_id=tenant_id,
                    created_by=user_id,
                )
                self.session.add(item)
                sort_idx += 1

        await self.session.commit()

        # 重新加载（含 items）
        from sqlalchemy.orm import selectinload
        result = await self.session.execute(
            select(QuotationSheet)
            .where(QuotationSheet.id == sheet.id)
            .options(selectinload(QuotationSheet.items))
        )
        return result.scalar_one()

    def _detect_categories(self, project: BidProject) -> list[str]:
        """从招标要求中推断需要报价的品类"""
        all_text = " ".join(
            r.content for r in project.requirements
        ).lower() if project.requirements else ""

        # 如果招标要求中提到了具体品类，只用提到的
        detected = []
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            if any(kw in all_text for kw in keywords):
                detected.append(cat)

        # 如果没有检测到任何品类（或要求太笼统），默认全部六大品类
        if not detected:
            detected = list(_DEFAULT_ITEMS.keys())

        return detected
