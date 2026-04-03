"""
投标准备检查清单服务

功能:
  1. 保证金备注模板生成
  2. 盖章/签字清单提取
  3. 打印装订后提醒项（物理交付检查）

架构红线: 纯规则提取，不调用 LLM
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("freshbid")


# ══════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════

@dataclass
class DepositMemo:
    """保证金备注模板"""
    amount: Optional[str] = None       # 金额
    account: Optional[str] = None      # 收款账户
    memo_text: str = ""                # 可直接复制的备注文本
    raw_requirement: str = ""          # 原始招标要求


@dataclass
class StampItem:
    """盖章/签字项"""
    document_name: str                 # 文件名称
    stamp_type: str                    # 公章 / 法人章 / 骑缝章 / 签字
    source: str                        # 来自哪条招标要求
    checked: bool = False              # 是否已完成


@dataclass
class PrintReminder:
    """打印装订后提醒项"""
    item: str                          # 检查项描述
    category: str                      # 装订 / 密封 / 份数 / 标记 / 递交
    checked: bool = False


@dataclass
class BidChecklist:
    """投标准备检查清单"""
    deposit_memo: Optional[DepositMemo] = None
    stamp_items: list[StampItem] = field(default_factory=list)
    print_reminders: list[PrintReminder] = field(default_factory=list)
    total_items: int = 0
    completed_items: int = 0


# ══════════════════════════════════════════════════════════════
# 1. 保证金备注模板
# ══════════════════════════════════════════════════════════════

_DEPOSIT_PATTERNS = {
    "amount": re.compile(r'保证金[金额为]*\s*[:：]?\s*(\d[\d,.]*)\s*[万元]'),
    "account": re.compile(r'(?:汇入|转入|账[户号])\s*[:：]?\s*([\u4e00-\u9fff\w]+银行[\u4e00-\u9fff\w]*?)(?:[，。；\s]|$)'),
}


def generate_deposit_memo(
    project_name: str,
    project_no: Optional[str] = None,
    lot_no: Optional[str] = None,
    tender_requirements: Optional[list[str]] = None,
) -> DepositMemo:
    """生成保证金转账备注模板

    Args:
        project_name: 项目名称
        project_no: 项目编号（如有）
        lot_no: 标段号（如有）
        tender_requirements: 招标文件中保证金相关条款文本列表
    """
    memo = DepositMemo()

    # 从招标要求中提取金额和账户
    if tender_requirements:
        combined = " ".join(tender_requirements)
        memo.raw_requirement = combined[:500]

        amt_match = _DEPOSIT_PATTERNS["amount"].search(combined)
        if amt_match:
            memo.amount = amt_match.group(1)

        acct_match = _DEPOSIT_PATTERNS["account"].search(combined)
        if acct_match:
            memo.account = acct_match.group(1)

    # 组装备注文本
    parts = [project_name]
    if project_no:
        parts.append(f"（项目编号：{project_no}）")
    if lot_no:
        parts.append(f"（{lot_no}）")
    parts.append("投标保证金")

    memo.memo_text = "".join(parts)

    return memo


# ══════════════════════════════════════════════════════════════
# 2. 盖章/签字清单
# ══════════════════════════════════════════════════════════════

# 需盖章的关键词模式
_STAMP_KEYWORDS = [
    (re.compile(r'(?:加盖|盖有|需盖|须盖)\s*(?:投标人|供应商|单位)?\s*(公章)'), "公章"),
    (re.compile(r'法[定人]*代表[人]?\s*(?:签[字署名]|盖章)'), "法人签字"),
    (re.compile(r'(?:骑缝章|骑缝处盖章)'), "骑缝章"),
    (re.compile(r'(?:签字|签署)\s*(?:并|和|及)?\s*盖章'), "签字盖章"),
    (re.compile(r'(?:逐页|每页)\s*(?:加盖|盖)\s*(?:公章|印章)'), "逐页盖章"),
    (re.compile(r'(?:授权委托书|授权书)'), "授权委托书（需盖章）"),
]

# 常见需盖章的文件类型
_STAMP_DOCUMENTS = [
    "投标函", "投标报价表", "法人授权委托书", "资格审查表",
    "技术服务方案", "投标保证金缴纳凭证", "企业资质复印件",
    "业绩证明材料", "信用承诺书", "廉洁投标承诺书",
    "客户满意度反馈表", "食品安全承诺书", "售后服务承诺书",
]


def extract_stamp_items(
    tender_requirements: Optional[list[str]] = None,
) -> list[StampItem]:
    """从招标要求中提取盖章/签字清单

    Args:
        tender_requirements: 招标文件中所有要求条款文本列表
    """
    items: list[StampItem] = []
    seen: set[str] = set()

    if not tender_requirements:
        return _default_stamp_items()

    combined = " ".join(tender_requirements)

    # 1. 关键词模式匹配
    for pattern, stamp_type in _STAMP_KEYWORDS:
        matches = pattern.finditer(combined)
        for match in matches:
            # 提取上下文作为文件名
            start = max(0, match.start() - 30)
            context = combined[start:match.end() + 20]
            # 尝试提取具体文件名
            doc_match = re.search(r'[\u4e00-\u9fff]{2,10}(?:表|书|函|单|件|证|材料)', context)
            doc_name = doc_match.group(0) if doc_match else context[:20].strip()
            key = f"{doc_name}_{stamp_type}"
            if key not in seen:
                seen.add(key)
                items.append(StampItem(
                    document_name=doc_name,
                    stamp_type=stamp_type,
                    source=context.strip()[:80],
                ))

    # 2. 补充常见文件
    for doc in _STAMP_DOCUMENTS:
        if doc in combined:
            key = f"{doc}_公章"
            if key not in seen:
                seen.add(key)
                items.append(StampItem(
                    document_name=doc,
                    stamp_type="公章",
                    source=f"招标文件提及「{doc}」",
                ))

    return items if items else _default_stamp_items()


def _default_stamp_items() -> list[StampItem]:
    """默认盖章清单（无法从招标文件提取时的兜底）"""
    defaults = [
        ("投标函", "公章"),
        ("投标报价表", "公章"),
        ("法人授权委托书", "法人签字盖章"),
        ("资格审查表", "公章"),
        ("技术服务方案（每页）", "骑缝章"),
        ("投标文件正本封面", "公章"),
    ]
    return [
        StampItem(document_name=name, stamp_type=stype, source="通用默认项")
        for name, stype in defaults
    ]


# ══════════════════════════════════════════════════════════════
# 3. 打印装订后提醒
# ══════════════════════════════════════════════════════════════

_DEFAULT_PRINT_REMINDERS = [
    # 装订
    ("正本与副本是否分别装订", "装订"),
    ("目录页码与实际页码是否一致", "装订"),
    ("所有附件是否齐全并装入", "装订"),
    # 密封
    ("投标文件是否密封并在封口处盖章", "密封"),
    ("密封袋上是否标注项目名称和投标人名称", "密封"),
    ("密封袋上是否注明「开标前不得拆封」", "密封"),
    # 份数与标记
    ("正本数量是否符合招标文件要求", "份数"),
    ("副本数量是否符合招标文件要求", "份数"),
    ("正本/副本是否在封面明确标注", "标记"),
    ("电子版U盘是否已拷入（如要求）", "份数"),
    # 递交
    ("投标截止时间已确认", "递交"),
    ("开标地点已确认", "递交"),
    ("携带法人身份证或授权委托书原件", "递交"),
    ("携带营业执照副本原件（备查验）", "递交"),
    ("保证金是否已确认到账", "递交"),
]


def get_print_reminders(
    copies_required: Optional[str] = None,
    has_electronic: bool = False,
) -> list[PrintReminder]:
    """获取打印装订后提醒清单

    Args:
        copies_required: 招标文件要求的份数描述（如 "正本1份，副本3份"）
        has_electronic: 是否要求提交电子版
    """
    reminders = [
        PrintReminder(item=item, category=cat)
        for item, cat in _DEFAULT_PRINT_REMINDERS
    ]

    # 根据具体份数要求补充
    if copies_required:
        reminders.insert(0, PrintReminder(
            item=f"份数要求确认: {copies_required}",
            category="份数",
        ))

    if has_electronic:
        reminders.append(PrintReminder(
            item="电子版文件格式是否符合要求（PDF/Word）",
            category="份数",
        ))

    return reminders


# ══════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════

def generate_bid_checklist(
    project_name: str,
    project_no: Optional[str] = None,
    lot_no: Optional[str] = None,
    tender_requirements: Optional[list[str]] = None,
    copies_required: Optional[str] = None,
    has_electronic: bool = False,
) -> BidChecklist:
    """生成投标准备完整检查清单

    Args:
        project_name: 项目名称
        project_no: 项目编号
        lot_no: 标段号
        tender_requirements: 招标文件要求条款文本列表
        copies_required: 份数要求描述
        has_electronic: 是否要求电子版

    Returns:
        BidChecklist 含保证金模板 + 盖章清单 + 打印提醒
    """
    deposit = generate_deposit_memo(project_name, project_no, lot_no, tender_requirements)
    stamps = extract_stamp_items(tender_requirements)
    reminders = get_print_reminders(copies_required, has_electronic)

    total = len(stamps) + len(reminders)

    return BidChecklist(
        deposit_memo=deposit,
        stamp_items=stamps,
        print_reminders=reminders,
        total_items=total,
        completed_items=0,
    )
