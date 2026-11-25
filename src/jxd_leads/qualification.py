"""Explainable ordering based solely on owner-confirmed dimensions."""


def priority(dimensions=None, confirmed=False, suppressed=False):
    if suppressed:
        return "停止联系"
    if not confirmed or not dimensions:
        return "常规核实"
    if dimensions.get("confidence") != "原文已核对":
        return "常规核实"
    if dimensions.get("fit") == "不符合":
        return "建议排除"
    if dimensions.get("need") == "明确暂无计划" or dimensions.get("timing") == "明确延期":
        return "暂缓"
    if (
        dimensions.get("fit") == "符合"
        and dimensions.get("need") == "明确需求"
        and dimensions.get("role") in {"已核实采购角色", "可影响/可引荐"}
    ):
        return "优先核实"
    return "常规核实"
