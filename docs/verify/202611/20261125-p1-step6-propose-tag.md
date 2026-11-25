# 第 6 步｜propose_tag 调研（不实现）

日期：2026-11-25
状态：只读调研，未新增工具、未改代码、未改表

## 事实

- `TOOL_NAMES` 仍为 18 个，末位是 `list_tags`。
- `list_tags` 已存在，Agent 可读取真实 `tag_id`。
- `add_tag(name, actor="owner")` 先调用 `_owner(actor)`，Agent 默认 actor 不是 owner，不能直接创建标签。
- 网页标签入口在 `workspace_web.py:156`，调用 `service.add_tag(data["name"])`，属本人操作路径。
- `propose_qualification` 与 `propose_opportunity_update` 可接收已有 `tag_ids`；`set_tags` 会校验标签真实存在。
- `submit_candidates` 不要求候选必须带标签，因此 Agent 提交候选前不需要新建标签。

## 判断

当前不需要第 19 个 `propose_tag` 工具。Agent 用 `list_tags` 获取已有标签即可完成候选提交和资格建议；确实缺少合适标签时，由本人通过工作台标签入口创建。

若未来确认需要让 Agent 提议新标签，应单独出方案并等本人批准，本轮不实现，不绕过 owner 权限直接写库。

## 触发条件

- 出现必须由 Agent 提议新标签、且本人不能及时在工作台创建的真实任务；
- 或标签缺失已成为候选提交的稳定阻塞点。
