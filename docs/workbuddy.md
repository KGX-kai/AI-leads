# WorkBuddy 接入（0.5.0 候选）

A1 起业务执行由 Codex 项目会话承接；本文件保留 WorkBuddy 兼容接入与既有 JSON/MCP 契约，不把兼容入口当成 Codex 已加载的证明。隔离候选验收必须使用候选解释器、候选源码和临时夹具，不能直接启动正式 0.3.0 的备用脚本。

固定工程入口 `.`。项目级 `.workbuddy/mcp.json` 保持原位置，不修改用户全局连接器。启动命令 `.venv/bin/python -m jxd_leads.mcp_server`，stdio 输出只承载协议。

先加载 [v1.2 业务提示词](workbuddy-v1.2.md)，再调用 `get_capabilities`。原生项目级工具发现和备用命令成功必须分别验收；旧版 WorkBuddy 5.9.3 原生发现未通过，历史上备用入口已实际回写公开候选。

备用入口在项目目录运行 `.venv/bin/python scripts/agent-call.py`，标准输入 JSON：

```json
{"tool":"get_capabilities","arguments":{}}
```

正式启用独立数据目录时，网页的 `serve --data-dir` 还要同时提供独立 `--approved-data-dir`；原生 MCP 连接器和备用脚本父进程分别提供 `JXD_DATA_DIR` 与 `JXD_APPROVED_DATA_DIR`。实际目录必须等于维护者批准的绝对路径。路径通过启动配置传入，不增加 stdin JSON 键或工具参数。
候选的 `scripts/agent-call.py` 切换稿只显式转传 `JXD_DATA_DIR` 和 `JXD_APPROVED_DATA_DIR` 给 MCP 子进程；SDK 默认不会继承这两个变量。缺失、空白、相对路径或两者不一致都会在子进程启动前拒绝，不再回落原默认 `data/`。数据库必须先由维护者用批准目录显式运行 `migrate`；三个入口有任何一个未配置或目录不一致，先停下核对。不要把整个环境变量集合转传。
缺少目录变量时，备用入口返回具体的数据目录错误，不再笼统报“工具或输入格式不正确”。本隔离候选没有独立 `.venv`，因此备用入口在当前目录不可直接运行；正式切换包必须先在候选目录建立 `.venv` 并安装依赖。脚本会先检查 `.venv/bin/python`，缺失时在 MCP 子进程启动前给出明确错误，不会回落到其他解释器或正式工程。本轮以临时 MCP 探针验证转传及协议，不能直接调用正式脚本来冒充候选验收。

正式切换前必须同步四项：`serve` 启动器同时传 `--data-dir` 和 `--approved-data-dir`；WorkBuddy 项目级 MCP 配置设置 `JXD_DATA_DIR` 与 `JXD_APPROVED_DATA_DIR`；候选目录存在 `.venv`；WorkBuddy 调用 `create_research_task` 时显式传 `region`、`scene`，并用同一 `request_id` 验证回执。以上任一项缺失，服务或 MCP 应在启动前停止。

允许18个受限工具：get_capabilities、create_research_task、get_research_task、submit_candidates、get_today_queue、list_candidates、search_projects、get_project_context、get_opportunity_context、propose_followup、propose_qualification、propose_opportunity_update、request_suppression、list_inquiries、get_inquiry_context、propose_inquiry_reply、propose_inquiry_fields、list_tags。

契约版本1.3：统一返回 schema_version/ok/request_id/data/error；业务失败同时设置 MCP isError，备用脚本非零退出。重试请求必须复用原编号；同编号不同内容会被拒绝。分页默认20、最多100；机会历史默认10。`submit_candidates` 可选公开单位电话、未知项、`source_channel`（取自 `get_capabilities.source_channels`）和 `bid_deadline`（不得早于 `published_at`）；工具名称与数量仍为18，标准输入调用协议及交接8键不变。

`create_research_task` 的参数名与类型保持原样；0.4.0 候选清除了旧的固定地区/场景默认值。省略两项会收到 `VALIDATION_ERROR`，须由本人明确本次范围后传入。WorkBuddy 若依赖旧默认调用，正式切换前必须改用显式参数并完成同任务编号回执验证。
调用时显式填写 `request_id`、`region`、`scene` 和本次 `target`；同次已保存请求重试复用原编号与相同内容。已有网页任务直接使用实际 `task_id`，不要另建一次。缺少范围时先取得本人指令，不能从旧任务、测试样例或看板示例推断。

新增工具不提供审核、正式报价、解除停联、任意SQL/命令或客户发送能力。Web 与 MCP 共享业务服务。相同系统账号下其他程序的任意Shell不属于此MCP的权限沙箱，助手不得用其他途径绕过审批。

企业号咨询自动接收与发送均保持关闭，后续接口见 [渠道协议](channel-adapter.md)。平台不新增付费API；WorkBuddy费用以实际账单为准。
