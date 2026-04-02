"""
Schema 验证测试 — TenderNoticeListOut Pydantic 模型
"""
import pytest
from app.schemas.tender_notice import TenderNoticeListOut


def test_tender_notice_list_out_valid():
    """完整字段可正常解析"""
    data = {
        "id": 1,
        "title": "XX学校食材配送项目",
        "status": "analyzed",
        "match_score": 80.5,
        "created_at": None,
    }
    obj = TenderNoticeListOut.model_validate(data)
    assert obj.id == 1
    assert obj.title == "XX学校食材配送项目"
    assert obj.status == "analyzed"
    assert obj.match_score == 80.5
    assert obj.recommendation is None


def test_tender_notice_list_out_minimal():
    """仅必填字段（id, title, status）可正常解析"""
    data = {"id": 2, "title": "测试项目", "status": "new"}
    obj = TenderNoticeListOut.model_validate(data)
    assert obj.id == 2
    assert obj.match_score is None


def test_tender_notice_list_out_missing_required():
    """缺少必填字段 → ValidationError"""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TenderNoticeListOut.model_validate({"id": 1})
