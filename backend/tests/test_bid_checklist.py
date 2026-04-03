"""
投标准备检查清单服务测试 — 保证金 + 盖章 + 打印提醒
"""
import pytest
from app.services.bid_checklist_service import (
    generate_deposit_memo,
    extract_stamp_items,
    get_print_reminders,
    generate_bid_checklist,
    DepositMemo,
    StampItem,
    PrintReminder,
    BidChecklist,
)


# ═══════════════════════════════════════════════════════════
# 保证金备注模板
# ═══════════════════════════════════════════════════════════

class TestDepositMemo:

    def test_basic_memo(self):
        """基本备注文本包含项目名"""
        memo = generate_deposit_memo("阳光小学2026年食材配送采购")
        assert "阳光小学" in memo.memo_text
        assert "投标保证金" in memo.memo_text

    def test_memo_with_project_no(self):
        """包含项目编号"""
        memo = generate_deposit_memo("食材配送采购", project_no="YGXX-2026-003")
        assert "YGXX-2026-003" in memo.memo_text

    def test_memo_with_lot(self):
        """包含标段号"""
        memo = generate_deposit_memo("食材配送", lot_no="第一标段")
        assert "第一标段" in memo.memo_text

    def test_extract_amount_from_requirements(self):
        """从招标要求提取保证金金额"""
        reqs = ["投标保证金金额为50000元，须在开标前汇入指定账户"]
        memo = generate_deposit_memo("测试项目", tender_requirements=reqs)
        assert memo.amount == "50000"

    def test_no_requirements_still_works(self):
        """无招标要求时仍生成基本备注"""
        memo = generate_deposit_memo("测试项目")
        assert memo.memo_text
        assert memo.amount is None


# ═══════════════════════════════════════════════════════════
# 盖章清单
# ═══════════════════════════════════════════════════════════

class TestStampItems:

    def test_extract_from_requirements(self):
        """从招标要求提取盖章项"""
        reqs = [
            "投标函须加盖投标人公章",
            "法定代表人签字并盖章",
            "技术方案须逐页加盖公章",
            "投标文件须加盖骑缝章",
        ]
        items = extract_stamp_items(reqs)
        types = {i.stamp_type for i in items}
        assert "公章" in types
        assert len(items) >= 3

    def test_default_when_no_requirements(self):
        """无招标要求时返回默认盖章清单"""
        items = extract_stamp_items(None)
        assert len(items) >= 4
        names = {i.document_name for i in items}
        assert "投标函" in names

    def test_document_matching(self):
        """识别常见需盖章文件"""
        reqs = ["投标人须提供客户满意度反馈表，并加盖公章"]
        items = extract_stamp_items(reqs)
        names = [i.document_name for i in items]
        assert any("满意度" in n for n in names)

    def test_no_duplicates(self):
        """不产生重复项"""
        reqs = ["投标函须加盖公章", "投标函需盖单位公章", "投标函加盖投标人公章"]
        items = extract_stamp_items(reqs)
        # 投标函相关不应出现太多重复
        names = [i.document_name for i in items]
        assert len(names) == len(set(f"{n}_{items[i].stamp_type}" for i, n in enumerate(names)))


# ═══════════════════════════════════════════════════════════
# 打印装订提醒
# ═══════════════════════════════════════════════════════════

class TestPrintReminders:

    def test_default_reminders(self):
        """默认提醒项覆盖装订/密封/份数/递交"""
        reminders = get_print_reminders()
        categories = {r.category for r in reminders}
        assert "装订" in categories
        assert "密封" in categories
        assert "份数" in categories
        assert "递交" in categories

    def test_copies_required(self):
        """指定份数要求时插入提醒"""
        reminders = get_print_reminders(copies_required="正本1份，副本3份")
        first = reminders[0]
        assert "正本1份" in first.item

    def test_electronic_required(self):
        """要求电子版时补充提醒"""
        reminders = get_print_reminders(has_electronic=True)
        items = [r.item for r in reminders]
        assert any("电子版" in i for i in items)

    def test_all_unchecked(self):
        """初始状态全部未勾选"""
        reminders = get_print_reminders()
        assert all(not r.checked for r in reminders)


# ═══════════════════════════════════════════════════════════
# 完整检查清单
# ═══════════════════════════════════════════════════════════

class TestBidChecklist:

    def test_full_checklist(self):
        """完整清单包含三大模块"""
        reqs = ["投标保证金金额为20000元", "投标函须加盖公章"]
        checklist = generate_bid_checklist(
            project_name="育才中学食材配送",
            project_no="YC-2026-001",
            lot_no="第一标段",
            tender_requirements=reqs,
            copies_required="正本1份，副本2份",
        )

        assert checklist.deposit_memo is not None
        assert "育才中学" in checklist.deposit_memo.memo_text
        assert len(checklist.stamp_items) >= 1
        assert len(checklist.print_reminders) >= 10
        assert checklist.total_items > 0
        assert checklist.completed_items == 0

    def test_minimal_checklist(self):
        """最小参数也能生成清单"""
        checklist = generate_bid_checklist(project_name="测试项目")
        assert checklist.deposit_memo is not None
        assert len(checklist.stamp_items) >= 4  # 默认清单
        assert len(checklist.print_reminders) >= 10
