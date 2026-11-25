# 开源敏感面只读预检 r01（4A）

- 日期：2026-11-25
- 结论：**未发现真实凭据、私钥、身份证号或可识别的真实客户数据**。主要暴露面是 36 个 tracked 文件中的本机绝对路径，以及 git 历史中仍可达的 4 个 Satoshi 字体 blob。
- 范围：`git log -p --all` 全历史 36 commits、`git ls-files` 224 个文件、55 张 PNG、18 个直接/dev 依赖、78 个已安装发行包。
- 状态：4A 只读核查完成；4B 未执行；未 push、未建远程、未动 8765、未改任何代码。

## 0. 分支与工作树（事实）

| 项 | 值 |
|---|---|
| 主工程 | `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05` |
| 主工程分支 / HEAD | `p1-fixes-20261125` / `1221934`，工作树干净 |
| 4A 执行分支 | `opensource-preflight-20261125`（worktree `/Users/dkai2024163.com/.codex/worktrees/ab3e/jingxiaodian-leads-v05`） |
| 4A 分支 HEAD | `1221934`，与主工程同点，工作树干净 |
| 独立测试 venv | worktree `.venv`，Python 3.12.11，`jxd_leads` 指向 worktree `src` |

> 口径冲突说明：本任务头写“分支 p1-fixes-20261125”，但开工前置指令要求“从 1221934 切出 `opensource-preflight-20261125`，确认后再继续 4A”。本报告提交在 `opensource-preflight-20261125`，未写入 P1 分支。若需改提，`1221934` 同点，单条 cherry-pick 即可。

## 1. 敏感信息全历史扫描

### 1.1 方法与判定口径

对 `git log -p --all` 全量 2.8 MB 补丁流逐行解析，按“当前 commit + 文件 + 新文件行号”归位。正则覆盖：凭据关键词、手机号、身份证、邮箱、内网 IP、本机路径，另加私钥头、`sk-`/`ghp_`/`AKIA`/`AIza`/`xox`/Fernet/JWT/Bearer 等高危前缀。

判定分类：`真实凭据` / `测试占位符` / `代码标识符` / `误报`。

### 1.2 结论汇总

| 类别 | 命中 | 判定 |
|---|---:|---|
| 私钥、云厂商密钥、GitHub/Slack token、Fernet、JWT | 0 | 无 |
| 身份证号 | 0 | 无 |
| 内网 IP（10/8、192.168/16、172.16/12） | 0 | 无 |
| 真实密码 / API key | 0 | 无 |
| 手机号 | 18 | 全部为合成占位号 |
| 邮箱 | 2 | 均为 `@pytest.mark...` 被正则误判 |
| 凭据关键词 | 63 | 全部为 CSRF、状态字段、变量名或日志措辞 |
| 本机绝对路径 | 208（历史）/ 193 行 / 36 文件（当前 HEAD） | 路径暴露，无业务数据 |

另外核验：`git rev-list --objects --all` 中不存在 `.db`、`.sqlite3`、`.pem`、`.key`、`.p12`、`.env` 任何历史 blob；历史最大 blob 为 `dashboard_v2.css`（1,111,462 B）与验收截图，无数据库或密钥文件。

### 1.3 手机号 18 处（逐条）

全部为 `13800000000`、`13900000000`、`13900000001`、`13800001111`、`13812345678` 及其 `+86` 变体；上下文为 `测试甲`、`测试乙`、`测试`、`恢复验证联系人`，属合成夹具。

| commit | 文件:行 | 文本摘录 |
|---|---|---|
| `42e30e8` | `docs/verify/202611/20261125-p1-all.diff:529` | `+    data = ContactInput(name="测试乙", channel="13900000000", role="采购")` |
| `5bd89e2` | `tests/test_inquiry_fields.py:103` | `iid, {"demand": "请联系 13800001111 讨论灯具"}, "合成测试中的号码", "fields-6"` |
| `5bd89e2` | `tests/test_inquiry_fields.py:106` | `assert "13800001111" not in svc.inquiry_context(iid)["demand"]` |
| `5bd89e2` | `tests/test_mcp_transport.py:88` | `"fields": {"status": "done", "demand": "请拨打 13800001111"},` |
| `5bd89e2` | `tests/test_mcp_transport.py:95` | `assert "13800001111" not in json.dumps(invalid_fields.structuredContent, ensure_ascii=False)` |
| `5bd89e2` | `tests/test_safety.py:33` | `data = ContactInput(name="测试甲", channel="13800000000", role="采购")` |
| `5bd89e2` | `tests/test_safety.py:42` | `assert "13800000000" not in json.dumps(svc.project_context(pid), ensure_ascii=False)` |
| `5bd89e2` | `tests/test_safety.py:43` | `assert b"13800000000" not in svc.db.path.read_bytes()` |
| `42e30e8` | `tests/test_safety.py:75` | `data = ContactInput(name="测试乙", channel="13900000000", role="采购")` |
| `5bd89e2` | `tests/test_safety.py:78` | `synthetic_id = "13812345678"` |
| `5bd89e2` | `tests/test_safety.py:95` | `svc.add_contact(pid, ContactInput(name="测试乙", channel="13900000000"))` |
| `5bd89e2` | `tests/test_safety.py:119` | `contact = svc.add_contact(pid, ContactInput(name="恢复验证联系人", channel="13900000001"))` |
| `c4b71b4` | `tests/test_safety.py:120` | `svc.add_contact(pid, ContactInput(name="测试乙", channel="13900000000"))` |
| `5bd89e2` | `tests/test_safety.py:226` | `contact = svc.add_contact(first, ContactInput(name="测试", channel="13800000000"))` |
| `5bd89e2` | `tests/test_safety.py:234` | `linked = svc.add_contact(second, ContactInput(name="测试", channel="+86 13800000000"))` |
| `5bd89e2` | `tests/test_safety.py:245` | `for value in ["13800000000", "+8613800000000", "+86 138 0000 0000", "0086-138-0000-0000"]:` |
| `c4b71b4` | `tests/test_safety.py:270` | 同上（历史版本） |
| `c4b71b4` | `tests/test_safety.py:276` | `assert redact("https://example.org/?phone=13800000000") == "https://example.org/?phone=[手机号已隐藏]"` |

判断：无可联系的真实号码；`13812345678` 虽非保留号段，但文件内显式命名 `synthetic_id`，用途为脱敏测试。

### 1.4 凭据关键词 63 处（逐条，判定均为测试占位符或代码标识符）

`+`/`-` 表示该行在补丁中是新增还是删除。

| commit | 文件:行 | 变更 | 判定 |
|---|---|---|---|
| `285e2a5` | `.githooks/pre-commit:44` | + | pre-commit 敏感文件名规则 |
| `6cb005f` | `docs/verify/202611/20261124-ENG-20261117-01-backup-wal.txt:44` | + | 门禁日志“视觉 token”措辞 |
| `6cb005f` | `docs/verify/202611/20261124-ENG-20261117-01-backup-wal.txt:77` | + | 门禁日志“视觉 token”措辞 |
| `6cb005f` | `docs/verify/202611/20261124-ENG-20261117-01-backup-wal.txt:108` | + | 门禁日志“视觉 token”措辞 |
| `6cb005f` | `docs/verify/202611/20261124-ENG-20261124-01-plan-r01.txt:12` | + | 门禁 PASS 字样 |
| `6cb005f` | `docs/verify/202611/20261124-ENG-20261124-01-plan-r01.txt:13` | + | 门禁 PASS 字样 |
| `6cb005f` | `docs/verify/202611/20261124-ENG-20261124-01-plan-r01.txt:78` | + | 门禁日志“视觉 token”措辞 |
| `6cb005f` | `docs/verify/202611/20261124-ENG-20261124-01-plan-r01.txt:106` | + | 门禁 PASS 字样 |
| `d086ec0` | `docs/verify/202611/20261124-SATOSHI-REMOVAL.txt:132` | + | 门禁日志“视觉 token”措辞 |
| `42e30e8` | `docs/verify/202611/20261125-p1-all.diff:572` | + | CSRF 会话令牌（测试） |
| `42e30e8` | `docs/verify/202611/20261125-p1-concurrency-probe.py:74` | + | CSRF 会话令牌（测试） |
| `42e30e8` | `docs/verify/202611/20261125-p1-concurrency-probe.py:84` | + | CSRF 会话令牌（测试） |
| `42e30e8` | `docs/verify/202611/20261125-p1-step7-preflight-final.txt:7` | + | 门禁日志“视觉 token”措辞 |
| `42e30e8` | `docs/verify/202611/20261125-p1-step7-preflight.txt:7` | + | 门禁日志“视觉 token”措辞 |
| `1221934` | `docs/verify/202611/20261125-p1-step8-final-preflight.txt:8` | + | 门禁日志“视觉 token”措辞 |
| `42e30e8` | `docs/verify/202611/20261125-p1-step9-notifications.txt:3` | + | 通知授权状态字段 |
| `42e30e8` | `docs/verify/202611/20261125-p1-step9-tech-debt.md:14` | + | 通知授权状态字段 |
| `5bd89e2` | `migrations/script.py.mako:10` | + | 模板 `pass` |
| `5bd89e2` | `migrations/script.py.mako:12` | + | 模板 `pass` |
| `42e30e8` | `native/notifications/main.swift:25` | + | 通知授权状态字段 |
| `4d526a7` | `native/notifications/main.swift:25` | + | 通知授权状态字段（stash 备份） |
| `42e30e8` | `native/notifications/main.swift:51` | + | 通知授权状态字段 |
| `4d526a7` | `native/notifications/main.swift:51` | + | 通知授权状态字段（stash 备份） |
| `5bd89e2` | `src/jxd_leads/backup.py:301` | + | `pass` 占位 |
| `64150f8` | `src/jxd_leads/dashboard_model.py:305` | + | 注释中的 credentials 措辞 |
| `5bd89e2` | `src/jxd_leads/db.py:280` | + | contextvars Token 变量 |
| `5bd89e2` | `src/jxd_leads/db.py:289` | + | contextvars Token 变量 |
| `5bd89e2` | `src/jxd_leads/desktop.py:23` | + | 通知授权状态字段 |
| `5bd89e2` | `src/jxd_leads/desktop.py:40` | + | 通知授权状态字段 |
| `5bd89e2` | `src/jxd_leads/models.py:13` | + | `pass` 占位 |
| `5bd89e2` | `src/jxd_leads/schemas.py:41` | + | URL 中拒绝账号口令的校验 |
| `c4b71b4` | `src/jxd_leads/security.py:196` | + | 脱敏正则变量 `token` |
| `c4b71b4` | `src/jxd_leads/security.py:197` | + | 脱敏正则变量 `token` |
| `c4b71b4` | `src/jxd_leads/security.py:198` | + | 脱敏正则变量 `token` |
| `c4b71b4` | `src/jxd_leads/security.py:199` | + | 脱敏正则变量 `token` |
| `c4b71b4` | `src/jxd_leads/security.py:200` | + | 脱敏正则变量 `token` |
| `c4b71b4` | `src/jxd_leads/service.py:104` | + | Vault 解密字段变量 `secret` |
| `c4b71b4` | `src/jxd_leads/service.py:105` | + | Vault 解密字段变量 `secret` |
| `5bd89e2` | `src/jxd_leads/service.py:433` | + | Vault 解密字段变量 |
| `5bd89e2` | `src/jxd_leads/service.py:437` | + | 掩码输出字段 |
| `5bd89e2` | `src/jxd_leads/service.py:438` | + | 掩码输出字段 |
| `5bd89e2` | `src/jxd_leads/static/app.js:14` | + | CSRF 请求头 |
| `5bd89e2` | `src/jxd_leads/static/htmx.min.js:1` | + | 第三方库压缩代码 |
| `5bd89e2` | `src/jxd_leads/templates/base.html:1` | + | CSRF meta 标签 |
| `5bd89e2` | `src/jxd_leads/templates/notifications.html:2` | + | 通知授权状态字段 |
| `5bd89e2` | `src/jxd_leads/web.py:172` | + | CSRF 校验 |
| `5bd89e2` | `src/jxd_leads/web.py:384` | + | 通知授权状态字段 |
| `5bd89e2` | `src/jxd_leads/workflows.py:433` | + | URL 中拒绝账号口令的校验 |
| `5bd89e2` | `tests/test_inquiry_fields.py:82` | + | CSRF 测试取参 |
| `dd32fb9` | `tests/test_marketing_fields.py:161` | + | CSRF 测试取参 |
| `5bd89e2` | `tests/test_quality_workbench.py:179` | + | CSRF 测试取参 |
| `5bd89e2` | `tests/test_quality_workbench.py:204` | + | CSRF 测试取参 |
| `5bd89e2` | `tests/test_quality_workbench.py:375` | + | CSRF 测试取参 |
| `5bd89e2` | `tests/test_quality_workbench.py:521` | + | CSRF 测试取参 |
| `5bd89e2` | `tests/test_safety.py:177` | + | CSRF 测试取参 |
| `5bd89e2` | `tests/test_safety.py:181` | + | CSRF 请求头 |
| `5bd89e2` | `tests/test_safety.py:187` | + | CSRF 请求头 |
| `42e30e8` | `tests/test_safety.py:240` | + | CSRF 测试取参 |
| `5bd89e2` | `tests/test_safety.py:253` | + | CSRF 测试取参 |
| `119278a` | `tests/test_upgrade.py:117` | + | `not-a-fernet-token` 非法令牌夹具 |
| `5bd89e2` | `tests/test_upgrade_review.py:148` | + | CSRF 测试取参 |
| `5bd89e2` | `tests/test_upgrade_review.py:324` | + | CSRF 测试取参 |
| `5bd89e2` | `tests/test_upgrade_review.py:345` | + | CSRF 测试取参 |

### 1.5 邮箱 2 处（误报）

| commit | 文件:行 | 说明 |
|---|---|---|
| `42e30e8` | `docs/verify/202611/20261125-p1-all.diff:459` | `+@pytest.mark.parametrize(` 被邮箱正则误判 |
| `42e30e8` | `docs/verify/202611/20261125-p1-step1.diff:92` | 同上 |

### 1.6 真实客户名核查

当前 HEAD 与全历史均未发现人名（无“先生/女士”命中）或可联系客户信息。仅两处含“公司”字样，均为示例：

- `tests/test_quality_workbench.py:16` `"company": "成都示例物业有限公司"` — 显式“示例”。
- `docs/dashboard-view-model-v0.4.0.json:35` `"client": "锦城物业"` — 文件 `meta.example = true`，同文件 `qtyNote` 为“示例值”，电话为 `138 **** 2140` 掩码；无地址、无完整联系方式。

判断：`锦城物业` 是“看起来像真实公司名”的示例，现实中可能存在同名企业，但该文件不具备可识别到具体客户的信息。可选优化（不属 4A）：4B 时改名为“示例物业”，或在 4B 报告中保留现状并说明。

### 1.7 历史中的 Satoshi 字体（新增发现，影响 4B）

`d51147e` 已从工作树删除 4 个 Satoshi `woff2`，但历史 blob 仍可达：

| blob | 路径 |
|---|---|
| `cf18cd4c` | `src/jxd_leads/static/dashboard/satoshi-300.woff2` |
| `81c40ab0` | `src/jxd_leads/static/dashboard/satoshi-400.woff2` |
| `ffd0ac96` | `src/jxd_leads/static/dashboard/satoshi-500.woff2` |
| `0a8db7a4` | `src/jxd_leads/static/dashboard/satoshi-700.woff2` |

判断：若带着完整历史公开发布，等于重新分发 Satoshi 字体文件，仍受 Indian Type Foundry Free Font License 约束；4B 的“wheel 内无 satoshi”不能覆盖这一点。需要在 4B 前拍板：压平历史后发布，或保留历史并补 ITF 许可文本。

## 2. 含 `/Users/dkai2024163.com` 的 tracked 文件

`git grep -n '/Users/'` 得 193 行，分布在 **36 个 tracked 文件**（任务预估约 33 个，实际 36 个）。

| 类别 | 文件数 | 行数 | 代表文件 | 暴露面性质 |
|---|---:|---:|---|---|
| README | 1 | 3 | `README.md` | 对外说明；工程/数据/归档绝对路径，无客户数据 |
| 提示词/接入说明 | 2 | 3 | `docs/workbuddy.md`、`docs/workbuddy-v1.2.md` | Agent 提示词与接入配置；含 v05、数据目录、已失效旧工程路径；无客户数据 |
| 操作手册 | 1 | 10 | `docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md` | hub 主控目录、`.Trash` 归档路径；流程说明，无客户数据 |
| 计划/SPEC | 1 | 11 | `docs/plan/SPEC-20261124-dashboard-v0.4.0.md` | hub worktree、Documents 聚合包路径；无客户数据 |
| 验收证据 | 31 | 166 | `docs/verify/202611/**` | 测试命令、venv/归档/快照绝对路径、合成夹具；无真实客户数据 |
| 源码 | 0 | 0 | — | `src/` 内无本机路径 |

重点明细：

- `docs/verify/202611/20261125-scope-taxonomy-r01.md` 44 行、`r02.md` 25 行、`20261125-p1-step8-scope-grep.txt` 43 行：路径密集，但均为本轮验收证据。
- `docs/workbuddy.md:5` 仍含死路径 `/Users/dkai2024163.com/ai/product/jingxiaodian-leads`；`4F` 清单只点名 README 与提示词，建议把该文件一并纳入相对化。
- `docs/京小电...r03.md:16/441` 已是 `.Trash/jingxiaodian-leads`（标注“已归档，仅历史查阅”），符合上一批口径。
- `src/`、`tests/`、`migrations/` 无任何 `/Users/` 命中，wheel 不会打包本机路径。

判断：路径暴露集中在文档与验收证据，属“本机目录结构暴露”，不含客户数据；`4F` 的“README/提示词相对化、verify 保留原貌”方案成立。

## 3. 55 张 PNG

总计 55 张、17,464,769 B（约 16.7 MB）。54 张在 `docs/verify/202611/`，1 张在源码静态资源。

| 目录 | 张数 | 合计字节 | 性质 |
|---|---:|---:|---|
| `docs/verify/202611/candidate-r04/` | 4 | 1,432,717 | 看板验收截图 |
| `docs/verify/202611/satoshi-removal/` | 2 | 947,239 | 字体移除前后截图 |
| `docs/verify/202611/theme-r02/` | 40 | 12,729,238 | 明暗主题 10 页 × 2 尺寸 × 2 主题 |
| `docs/verify/202611/theme-r03/` | 8 | 2,252,461 | 主题回归截图 |
| `src/jxd_leads/static/dashboard/` | 1 | 103,114 | `owner-avatar.png`（应用内头像） |

<details>
<summary>55 张逐项路径与大小</summary>

| 路径 | 字节 | 大小 |
|---|---:|---|
| `docs/verify/202611/candidate-r04/analytics-dark.png` | 322762 | 315.2 KB |
| `docs/verify/202611/candidate-r04/analytics-light.png` | 506630 | 494.8 KB |
| `docs/verify/202611/candidate-r04/schedule-dark.png` | 218331 | 213.2 KB |
| `docs/verify/202611/candidate-r04/schedule-light.png` | 384994 | 376.0 KB |
| `docs/verify/202611/satoshi-removal/overview-desktop-dark.png` | 602260 | 588.1 KB |
| `docs/verify/202611/satoshi-removal/overview-mobile-dark.png` | 344979 | 336.9 KB |
| `docs/verify/202611/theme-r02/analytics-1440-dark.png` | 351360 | 343.1 KB |
| `docs/verify/202611/theme-r02/analytics-1440-light.png` | 620026 | 605.5 KB |
| `docs/verify/202611/theme-r02/analytics-390-dark.png` | 190494 | 186.0 KB |
| `docs/verify/202611/theme-r02/analytics-390-light.png` | 359734 | 351.3 KB |
| `docs/verify/202611/theme-r02/detail-1440-dark.png` | 208415 | 203.5 KB |
| `docs/verify/202611/theme-r02/detail-1440-light.png` | 356597 | 348.2 KB |
| `docs/verify/202611/theme-r02/detail-390-dark.png` | 81264 | 79.4 KB |
| `docs/verify/202611/theme-r02/detail-390-light.png` | 119315 | 116.5 KB |
| `docs/verify/202611/theme-r02/leads-1440-dark.png` | 284180 | 277.5 KB |
| `docs/verify/202611/theme-r02/leads-1440-light.png` | 495642 | 484.0 KB |
| `docs/verify/202611/theme-r02/leads-390-dark.png` | 149823 | 146.3 KB |
| `docs/verify/202611/theme-r02/leads-390-light.png` | 254061 | 248.1 KB |
| `docs/verify/202611/theme-r02/opportunities-1440-dark.png` | 199439 | 194.8 KB |
| `docs/verify/202611/theme-r02/opportunities-1440-light.png` | 276155 | 269.7 KB |
| `docs/verify/202611/theme-r02/opportunities-390-dark.png` | 63279 | 61.8 KB |
| `docs/verify/202611/theme-r02/opportunities-390-light.png` | 82882 | 80.9 KB |
| `docs/verify/202611/theme-r02/overlay-1440-dark.png` | 362857 | 354.4 KB |
| `docs/verify/202611/theme-r02/overlay-1440-light.png` | 677375 | 661.5 KB |
| `docs/verify/202611/theme-r02/overlay-390-dark.png` | 269513 | 263.2 KB |
| `docs/verify/202611/theme-r02/overlay-390-light.png` | 518843 | 506.7 KB |
| `docs/verify/202611/theme-r02/overview-1440-dark.png` | 607690 | 593.4 KB |
| `docs/verify/202611/theme-r02/overview-1440-light.png` | 1106719 | 1080.8 KB |
| `docs/verify/202611/theme-r02/overview-390-dark.png` | 365750 | 357.2 KB |
| `docs/verify/202611/theme-r02/overview-390-light.png` | 657544 | 642.1 KB |
| `docs/verify/202611/theme-r02/projects-1440-dark.png` | 233422 | 228.0 KB |
| `docs/verify/202611/theme-r02/projects-1440-light.png` | 415631 | 405.9 KB |
| `docs/verify/202611/theme-r02/projects-390-dark.png` | 94713 | 92.5 KB |
| `docs/verify/202611/theme-r02/projects-390-light.png` | 141797 | 138.5 KB |
| `docs/verify/202611/theme-r02/reports-1440-dark.png` | 231249 | 225.8 KB |
| `docs/verify/202611/theme-r02/reports-1440-light.png` | 351469 | 343.2 KB |
| `docs/verify/202611/theme-r02/reports-390-dark.png` | 103942 | 101.5 KB |
| `docs/verify/202611/theme-r02/reports-390-light.png` | 142270 | 138.9 KB |
| `docs/verify/202611/theme-r02/schedule-1440-dark.png` | 274918 | 268.5 KB |
| `docs/verify/202611/theme-r02/schedule-1440-light.png` | 562747 | 549.6 KB |
| `docs/verify/202611/theme-r02/schedule-390-dark.png` | 117830 | 115.1 KB |
| `docs/verify/202611/theme-r02/schedule-390-light.png` | 198316 | 193.7 KB |
| `docs/verify/202611/theme-r02/settings-1440-dark.png` | 293133 | 286.3 KB |
| `docs/verify/202611/theme-r02/settings-1440-light.png` | 512875 | 500.9 KB |
| `docs/verify/202611/theme-r02/settings-390-dark.png` | 146436 | 143.0 KB |
| `docs/verify/202611/theme-r02/settings-390-light.png` | 249533 | 243.7 KB |
| `docs/verify/202611/theme-r03/analytics-1440-dark.png` | 380883 | 372.0 KB |
| `docs/verify/202611/theme-r03/analytics-1440-light.png` | 629609 | 614.9 KB |
| `docs/verify/202611/theme-r03/analytics-390-dark.png` | 213372 | 208.4 KB |
| `docs/verify/202611/theme-r03/analytics-390-light.png` | 356443 | 348.1 KB |
| `docs/verify/202611/theme-r03/opportunities-1440-dark.png` | 206841 | 202.0 KB |
| `docs/verify/202611/theme-r03/opportunities-1440-light.png` | 297955 | 291.0 KB |
| `docs/verify/202611/theme-r03/opportunities-390-dark.png` | 71161 | 69.5 KB |
| `docs/verify/202611/theme-r03/opportunities-390-light.png` | 96197 | 93.9 KB |
| `src/jxd_leads/static/dashboard/owner-avatar.png` | 103114 | 100.7 KB |

</details>

抽查判定（实际打开查看）：

| 文件 | 内容 | 判定 |
|---|---|---|
| `candidate-r04/analytics-light.png` | 渠道分析 1 候选、来源“招投标”，无客户名 | 合成夹具 |
| `candidate-r04/schedule-light.png` | 待办“待核实采购”“客户咨询：身份与需求待核实” | 合成夹具 |
| `theme-r02/leads-1440-light.png` | 5 条“合成照明项目 1–5”“合成灯具客户 1–5” | 合成夹具 |
| `theme-r02/detail-1440-light.png` | 详情页明文“合成主题验收数据，无真实客户信息” | 合成夹具 |
| `theme-r03/opportunities-1440-light.png` | “待核实采购”“合成区域照明” | 合成夹具 |

PNG 元数据：无 `exiftool`；用 `strings` 检索 Software/Artist/Copyright/Adobe/Photoshop/Figma 等关键字，5 张抽查均无命中。截图页脚只含版本与构建号（`rev-147cfd6a90e5`、`rev-9b78fa9d5d9`）。

判断：54 张验收截图均为合成数据；`owner-avatar.png` 为应用头像，不含可识别真人肖像特征（4B G 项将再确认来源声明）。

## 4. 依赖许可（18 个直接/dev 依赖）

数据来源：worktree `.venv` 的 `importlib.metadata`（已安装版本），检索日期 2026-11-25。运行时按 `pyproject.toml` 的 13 个直接依赖 + 5 个 dev 依赖。

| # | 包 | 版本 | 许可 | 风险标记 |
|---:|---|---|---|---|
| 1 | `fastapi` | 0.165.0 | MIT | 无 |
| 2 | `uvicorn` | 0.54.0 | BSD-3-Clause | 无 |
| 3 | `sqlalchemy` | 2.1.9 | MIT | 无 |
| 4 | `alembic` | 1.20.1 | MIT | 无 |
| 5 | `jinja2` | 3.1.6 | BSD（classifier） | 无 |
| 6 | `python-multipart` | 0.0.34 | Apache-2.0 | 无 |
| 7 | `itsdangerous` | 2.2.0 | BSD（classifier） | 无 |
| 8 | `cryptography` | 50.0.2 | Apache-2.0 OR BSD-3-Clause | 无 |
| 9 | `keyring` | 25.7.0 | MIT | 无 |
| 10 | `mcp` | 1.30.0 | MIT | 无 |
| 11 | `openpyxl` | 3.1.5 | MIT | 无 |
| 12 | `defusedxml` | 0.7.1 | PSFL（PSF-2.0） | 宽松许可，需在 NOTICE 列明全称 |
| 13 | `filelock` | 4.3.1 | MIT | 无 |
| 14 | `pytest`（dev） | 9.2.0 | MIT | 无 |
| 15 | `httpx`（dev） | 0.28.1 | BSD-3-Clause | 无 |
| 16 | `pytest-asyncio`（dev） | 1.5.0 | Apache-2.0 | 无 |
| 17 | `ruff`（dev） | 0.17.6 | MIT | 无 |
| 18 | `pip-audit`（dev） | 2.10.1 | Apache-2.0（classifier；无 License 字段） | 许可字段缺失，按 classifier 记 |

关键结论：

- **GPL / AGPL / SSPL：0 项**（扫描全部 78 个已安装发行包）。
- 唯一弱 copyleft 传递依赖：`certifi 2026.11.20`，**MPL-2.0**，由 `httpcore`（经 `httpx`/`mcp` 运行时链）与 `requests`（pip-audit）引入。MPL-2.0 是文件级 copyleft，不要求本项目开源，但分发时需保留其许可与来源。
- `pip_api 0.0.35`（pip-audit 传递依赖）为 Apache-2.0，元数据为完整协议正文，非风险项。
- 直接依赖全部为 MIT/BSD/Apache/PSF 系列，与 Apache-2.0 发布兼容。

## 5. `dashboard_v2.js` 第三方代码检查

| 检查项 | 结果 |
|---|---|
| 文件大小 | 16,605 B（非压缩、可读） |
| 结构 | 自执行 IIFE，首行 `(() => { "use strict"; ...`，为项目自有看板脚本 |
| CDN / 外链 | 无；唯一 URL 是 `http://www.w3.org/2000/svg` 命名空间（`createElementNS`） |
| 版权头 / `@license` / `Copyright` | 无 |
| 第三方库名 | 无（jQuery、React、Vue、Chart.js 等均未出现） |

判断：`dashboard_v2.js` 为第一方代码，不含第三方片段。

附带发现（影响 4B H 项）：

- `dashboard_v2.css` 为 978,571 B，含 **4 段 `@font-face` 内嵌 Poppins TTF base64**（400/500/600/700），不是 Satoshi。
- `htmx.min.js` 为第三方 2.0.8（0BSD），文件内无版权头，许可仅靠 `NOTICE.md` 记录。
- `src/` 内无任何 Satoshi 文件；工作树 `rg -i satoshi src/` 为 0 命中。

## 6. 4B 前需要拍板的事项

| # | 事项 | 依据 | 建议 |
|---:|---|---|---|
| 1 | 是否带完整 git 历史发布 | 历史仍可达 4 个 Satoshi `woff2` blob（`d51147e` 仅删工作树） | 推荐用 orphan/压平快照对外发布，内部保留完整历史；否则须在 NOTICE 补 ITF 许可并接受字体再分发条款 |
| 2 | `docs/workbuddy.md` 死路径 | 第 5 行仍写 `/ai/product/jingxiaodian-leads` | 4F 一并改为 v05 或相对路径 |
| 3 | `dashboard_v2.css` 内嵌 Poppins | 4 段 base64 TTF，978 KB | 4B H 项同时验证“CSS 仅含 Poppins、不含 Satoshi”，THIRD_PARTY_LICENSES 覆盖内嵌副本 |
| 4 | `NOTICE.md` 现状 | 仍列 4 行 Satoshi，无 Apache-2.0 声明 | 4B B 项按计划重写为 `NOTICE` |
| 5 | `docs/dashboard-view-model-v0.4.0.json` 示例名“锦城物业” | `meta.example=true`，无联系方式 | 可选改为“示例物业”；不改也不构成真实客户数据 |
| 6 | 文件计数差异 | 任务预估约 33 个，实测 36 个 | 以实测为准；4F 按类别处理，不按数字处理 |

## 7. 证据文件

| 文件 | 内容 |
|---|---|
| `docs/verify/202611/20261125-opensource-preflight-r01-scan.tsv` | 291 条命中逐行明细（commit/文件/行号/判定/原文） |
| `docs/verify/202611/20261125-opensource-preflight-r01-commands.txt` | 本轮命令与关键原始输出 |
| `/Users/dkai2024163.com/WorkBuddy/2026-11-25-10-38-06/20261125-4A-opensource-preflight/raw/all-history.txt` | `git log -p --all` 全量 2.8 MB 原始补丁流 |
| `/Users/dkai2024163.com/WorkBuddy/2026-11-25-10-38-06/20261125-4A-opensource-preflight/raw/hits.json` | 正则命中结构化原始数据 |
| `/Users/dkai2024163.com/WorkBuddy/2026-11-25-10-38-06/20261125-4A-opensource-preflight/raw/{local-paths,png-list,largest-blobs}.txt` | 路径、PNG、历史大对象原始清单 |

## 8. 判定

- **事实**：无真实凭据、无私钥、无身份证、无内网 IP、无真实客户联系方式；手机号与邮箱命中均为测试或误报。
- **事实**：路径暴露 36 个 tracked 文件、193 行，全部在文档/验收证据；源码与 tests 无本机路径。
- **事实**：18 个直接/dev 依赖无 GPL/AGPL/SSPL；传递依赖 `certifi` 为 MPL-2.0。
- **判断**：4A 未触发“发现真实凭据/真实客户数据立即停手”条件，可以进入 4B 评审；但历史 Satoshi 与 `docs/workbuddy.md` 死路径需先有结论。
