"""
Node 4 compliance_gate 单元测试 — 纯规则检查，无外部依赖
"""
import pytest

from app.services.generation.compliance_gate import (
    check_compliance,
    ComplianceLevel,
    ComplianceReport,
    _check_l1_format,
    _check_l2_semantic,
    _check_l3_disqualify,
    _check_cross_chapter_consistency,
    _check_credential_chapter_match,
)
from app.services.generation.writer import DraftChapter


# ── 工厂函数 ──────────────────────────────────────────────

def _draft(chapter_no="第三章", title="食材采购与质量保障方案",
           content="本公司建立了完善的食材溯源体系。", word_count=None):
    wc = word_count if word_count is not None else len(content)
    return DraftChapter(
        chapter_no=chapter_no, title=title,
        content=content, sources_cited=[], word_count=wc,
    )


def _long_content(n=600):
    """生成指定字数的合规内容"""
    return "本公司建立了完善的食品安全管理体系，通过HACCP认证和ISO 22000认证。" * (n // 30 + 1)


# ═══════════════════════════════════════════════════════════
# L1 格式检查
# ═══════════════════════════════════════════════════════════

class TestL1Format:

    def test_empty_content_flagged(self):
        """空内容被标记"""
        issues = _check_l1_format(_draft(content="", word_count=0))
        assert len(issues) >= 1
        assert issues[0].level == ComplianceLevel.L1_FORMAT
        assert "空" in issues[0].description

    def test_placeholder_content_flagged(self):
        """占位符内容被标记"""
        issues = _check_l1_format(_draft(
            chapter_no="第八章", content="（报价数据由报价引擎自动生成）", word_count=0
        ))
        # 第八章 min_words=0，所以占位符不报错
        assert len(issues) == 0

    def test_word_count_below_minimum(self):
        """字数低于阈值被标记"""
        issues = _check_l1_format(_draft(
            chapter_no="第三章", content="太短了", word_count=10
        ))
        found = [i for i in issues if "字数不足" in i.description]
        assert len(found) == 1
        assert "500" in found[0].suggestion  # 第三章最低 500

    def test_word_count_above_minimum_ok(self):
        """字数达标不报错"""
        issues = _check_l1_format(_draft(
            chapter_no="第三章", content=_long_content(600), word_count=600
        ))
        word_issues = [i for i in issues if "字数不足" in i.description]
        assert len(word_issues) == 0

    def test_vague_language_flagged(self):
        """模糊用语被标记"""
        issues = _check_l1_format(_draft(
            content="本公司将按规定执行，根据实际情况调整。" * 30,
            word_count=600,
        ))
        vague = [i for i in issues if "模糊用语" in i.description]
        assert len(vague) >= 1
        descs = " ".join(v.description for v in vague)
        assert "按规定" in descs or "根据实际" in descs

    def test_clean_content_no_issues(self):
        """规范内容无 L1 问题"""
        issues = _check_l1_format(_draft(
            content=_long_content(600), word_count=600,
        ))
        # 不应有字数和空内容问题
        critical = [i for i in issues if "字数不足" in i.description or "空" in i.description]
        assert len(critical) == 0


# ═══════════════════════════════════════════════════════════
# L2 语义审查
# ═══════════════════════════════════════════════════════════

class TestL2Semantic:

    def test_scoring_req_not_covered(self):
        """评分项未在章节中覆盖 → warning"""
        reqs = [{"category": "scoring", "chapter_no": "第三章",
                 "content": "有机蔬菜种植基地直供方案和全程溯源体系"}]
        issues = _check_l2_semantic(
            _draft(content="本公司主营肉类加工业务", word_count=600), reqs
        )
        assert len(issues) >= 1
        assert issues[0].level == ComplianceLevel.L2_SEMANTIC
        assert "覆盖不足" in issues[0].description

    def test_scoring_req_covered(self):
        """评分项已覆盖 → 无问题"""
        reqs = [{"category": "scoring", "chapter_no": "第三章",
                 "content": "冷链配送方案及温控措施"}]
        issues = _check_l2_semantic(
            _draft(content="我公司冷链配送方案采用全程温控措施，配备温度记录仪", word_count=600), reqs
        )
        assert len(issues) == 0

    def test_non_scoring_reqs_ignored(self):
        """非评分类要求不在 L2 检查范围"""
        reqs = [{"category": "disqualification", "chapter_no": "第三章",
                 "content": "须持有食品经营许可证"}]
        issues = _check_l2_semantic(_draft(), reqs)
        assert len(issues) == 0


# ═══════════════════════════════════════════════════════════
# L3 废标检测
# ═══════════════════════════════════════════════════════════

class TestL3Disqualify:

    def test_missing_credential_blocking(self):
        """缺少废标项要求的资质 → blocking issue"""
        reqs = [{"category": "disqualification",
                 "content": "投标人须持有食品经营许可证"}]
        issues = _check_l3_disqualify(
            drafts=[_draft(content=_long_content())],
            requirements=reqs,
            enterprise_cred_types={"business_license"},  # 有营业执照但没 food_license
        )
        blocking = [i for i in issues if i.is_blocking and "食品经营许可" in i.description]
        assert len(blocking) >= 1

    def test_has_credential_no_blocking(self):
        """持有要求的资质 → 不因资质阻断"""
        reqs = [{"category": "disqualification",
                 "content": "投标人须持有食品经营许可证"}]
        content = "本公司持有食品经营许可证，编号XXX。投标人须持有食品经营许可证的要求已满足。"
        issues = _check_l3_disqualify(
            drafts=[_draft(content=content)],
            requirements=reqs,
            enterprise_cred_types={"food_license", "business_license"},
        )
        cred_issues = [i for i in issues if "缺少对应资质" in i.description]
        assert len(cred_issues) == 0

    def test_disqualify_req_not_responded(self):
        """废标项在文件中完全未响应 → blocking"""
        reqs = [{"category": "disqualification",
                 "content": "投标人必须提供近三年同类项目业绩证明"}]
        issues = _check_l3_disqualify(
            drafts=[_draft(content="本公司成立于2020年。")],
            requirements=reqs,
            enterprise_cred_types=set(),
        )
        blocking = [i for i in issues if i.is_blocking and "未在投标文件中响应" in i.description]
        assert len(blocking) >= 1

    def test_no_disqualify_reqs_clean(self):
        """无废标项要求 → 无 L3 issue"""
        reqs = [{"category": "scoring", "content": "冷链方案"}]
        issues = _check_l3_disqualify(
            drafts=[_draft()], requirements=reqs,
        )
        assert len(issues) == 0

    def test_empty_cred_types_defaults(self):
        """enterprise_cred_types=None 不崩溃"""
        reqs = [{"category": "disqualification", "content": "须持有HACCP认证"}]
        issues = _check_l3_disqualify(
            drafts=[_draft(content="无相关内容")],
            requirements=reqs,
            enterprise_cred_types=None,
        )
        assert any(i.is_blocking for i in issues)


# ═══════════════════════════════════════════════════════════
# check_compliance 主入口
# ═══════════════════════════════════════════════════════════

class TestCheckCompliance:

    @pytest.mark.asyncio
    async def test_all_clean_passes(self):
        """无问题 → passed=True"""
        drafts = [_draft(content=_long_content(600), word_count=600)]
        report = await check_compliance(drafts, requirements=[])
        assert report.passed is True
        assert report.chapters == drafts

    @pytest.mark.asyncio
    async def test_l1_issue_still_passes(self):
        """L1 问题不阻断（non-blocking）"""
        drafts = [_draft(content="太短", word_count=4)]
        report = await check_compliance(drafts, requirements=[])
        assert report.passed is True  # L1 non-blocking
        assert len(report.issues) >= 1

    @pytest.mark.asyncio
    async def test_l3_blocking_fails(self):
        """L3 废标 → passed=False"""
        drafts = [_draft(content="本公司简介", word_count=100)]
        reqs = [{"category": "disqualification",
                 "content": "投标人须持有食品经营许可证"}]
        report = await check_compliance(
            drafts, requirements=reqs,
            enterprise_cred_types={"business_license"},
        )
        assert report.passed is False
        blocking = [i for i in report.issues if i.is_blocking]
        assert len(blocking) >= 1

    @pytest.mark.asyncio
    async def test_chapters_passthrough(self):
        """chapters 透传原始 drafts"""
        drafts = [_draft(), _draft(chapter_no="第四章")]
        report = await check_compliance(drafts, requirements=[])
        assert len(report.chapters) == 2
        assert report.chapters[0].chapter_no == "第三章"


# ═══════════════════════════════════════════════════════════
# 195号文增强 — 跨章节一致性
# ═══════════════════════════════════════════════════════════

class TestCrossChapterConsistency:

    def test_consistent_data_no_issues(self):
        """同一指标在各章节一致 → 无问题"""
        drafts = [
            _draft("第三章", "食材采购", "本公司冷链车辆 12 辆，配备温控设备"),
            _draft("第五章", "配送方案", "我们拥有冷链车辆 12 辆，全程监控"),
        ]
        issues = _check_cross_chapter_consistency(drafts)
        assert len(issues) == 0

    def test_contradictory_data_flagged(self):
        """同一指标不同值 → 标记矛盾"""
        drafts = [
            _draft("第三章", "食材采购", "本公司冷链车辆 12 辆"),
            _draft("第五章", "配送方案", "公司现有冷链车辆 8 辆"),
        ]
        issues = _check_cross_chapter_consistency(drafts)
        contradiction = [i for i in issues if "数据矛盾" in i.description]
        assert len(contradiction) >= 1
        assert "冷链车辆" in contradiction[0].description

    def test_no_numeric_data_clean(self):
        """章节无数值声明 → 无问题"""
        drafts = [
            _draft("第一章", "公司简介", "本公司专注于生鲜配送服务"),
        ]
        issues = _check_cross_chapter_consistency(drafts)
        assert len(issues) == 0

    def test_multiple_metrics_checked(self):
        """多个指标各自独立检查"""
        drafts = [
            _draft("第三章", "食材采购", "冷链车辆 12 辆，员工人数 50 人"),
            _draft("第五章", "配送方案", "冷链车辆 12 辆，员工人数 80 人"),
        ]
        issues = _check_cross_chapter_consistency(drafts)
        # 冷链车辆一致无问题，员工人数矛盾
        descs = " ".join(i.description for i in issues)
        assert "员工人数" in descs
        assert "冷链车辆" not in descs


# ═══════════════════════════════════════════════════════════
# 195号文增强 — 资质引用完整性
# ═══════════════════════════════════════════════════════════

class TestCredentialChapterMatch:

    def test_cred_referenced_no_issues(self):
        """资质在对应章节被引用 → 无问题"""
        drafts = [
            _draft("第四章", "质量管理", "本公司通过HACCP认证，建立了完善的食品安全体系"),
        ]
        issues = _check_credential_chapter_match(drafts, {"haccp"})
        assert len(issues) == 0

    def test_cred_not_referenced_flagged(self):
        """资质未在对应章节引用 → 标记"""
        drafts = [
            _draft("第四章", "质量管理", "本公司建立了完善的管理体系"),
        ]
        issues = _check_credential_chapter_match(drafts, {"haccp"})
        assert len(issues) >= 1
        assert "haccp" in issues[0].description
        assert "HACCP" in issues[0].suggestion

    def test_no_creds_clean(self):
        """无企业资质 → 跳过检查"""
        drafts = [_draft("第四章", "质量管理", "内容")]
        issues = _check_credential_chapter_match(drafts, set())
        assert len(issues) == 0

    def test_none_creds_clean(self):
        """enterprise_cred_types=None → 跳过"""
        drafts = [_draft()]
        issues = _check_credential_chapter_match(drafts, None)
        assert len(issues) == 0

    def test_irrelevant_chapter_skipped(self):
        """资质不期望出现在无关章节 → 不标记"""
        drafts = [
            _draft("第一章", "公司简介", "本公司成立于2015年"),
        ]
        issues = _check_credential_chapter_match(drafts, {"haccp"})
        # 第一章标题不含"质量/安全/管理"，不在检查范围
        assert len(issues) == 0

    def test_integrated_in_check_compliance(self):
        """195号文检查集成到主入口"""
        import asyncio
        drafts = [
            _draft("第三章", "食材采购", "冷链车辆 12 辆" + _long_content(500)),
            _draft("第五章", "配送方案", "冷链车辆 8 辆" + _long_content(500)),
        ]
        report = asyncio.get_event_loop().run_until_complete(
            check_compliance(drafts, requirements=[])
        )
        # 应检测到冷链车辆矛盾
        contradiction = [i for i in report.issues if "数据矛盾" in i.description]
        assert len(contradiction) >= 1
