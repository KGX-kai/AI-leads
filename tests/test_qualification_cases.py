import pytest

from jxd_leads.qualification import priority

BASE = {"fit": "符合", "need": "明确需求", "role": "已核实采购角色", "confidence": "原文已核对", "timing": "未知"}
# Synthetic manually labelled rule cases; these are not an estimate of real conversion or AI extraction accuracy.
CASES = [
    ("明确询价且采购角色已核实", {}, True, False, "优先核实"),
    ("补货需求和角色已核实", {"timing": "已明确日期/窗口"}, True, False, "优先核实"),
    ("可引荐到已知项目", {"role": "可影响/可引荐"}, True, False, "优先核实"),
    ("仅行业匹配", {"need": "未知", "role": "未知"}, True, False, "常规核实"),
    ("供应商地址当项目位置待核", {"fit": "待核实"}, True, False, "常规核实"),
    ("只有历史中标", {"need": "未知"}, True, False, "常规核实"),
    ("来源不可达", {"confidence": "待核对"}, True, False, "常规核实"),
    ("同名项目地址冲突", {"confidence": "存在冲突"}, True, False, "常规核实"),
    ("地域明确不符", {"fit": "不符合"}, True, False, "建议排除"),
    ("产品需求明确不符", {"fit": "不符合", "role": "未知"}, True, False, "建议排除"),
    ("暂无预算不等于无效", {"budget": "未知"}, True, False, "优先核实"),
    ("暂无回复不等于无效", {"reply": "未知"}, True, False, "优先核实"),
    ("明确无采购权", {"role": "明确无权限"}, True, False, "常规核实"),
    ("明确采购延期", {"timing": "明确延期"}, True, False, "暂缓"),
    ("明确暂无采购计划", {"need": "明确暂无计划"}, True, False, "暂缓"),
    ("设备有问题但采购未定", {"need": "有问题但采购未定"}, True, False, "常规核实"),
    ("AI给出高意向但未审", {}, False, False, "常规核实"),
    ("AI建议排除但未审", {"fit": "不符合"}, False, False, "常规核实"),
    ("拒绝优先于明确需求", {}, True, True, "停止联系"),
    ("拒绝优先于未审建议", {}, False, True, "停止联系"),
]


@pytest.mark.parametrize("label,changes,confirmed,suppressed,expected", CASES, ids=[c[0] for c in CASES])
def test_ordering_cases(label, changes, confirmed, suppressed, expected):
    assert priority(BASE | changes, confirmed, suppressed) == expected
