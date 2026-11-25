# 第三步 B · P1 修复最终状态 r02

日期：2026-11-25
工作目录：`/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05`
分支：`p1-fixes-20261125`
提交：`42e30e80a40b36ef55d0d6811a928a8bd71af2d6`
提交信息：`feat(p1): enforce six-day window, csv audit, idempotency and suppress guards`

## 结论

第 1–9 步已完成，第 8 步统一切换通过。8765 现由 PID `13511` 运行 v05 `0.5.0`，`/health` 正常，8 页均 200，MCP `schema 1.3`、18 工具，迁移头仍为 `20261124_marketing_fields`。10 分钟观察窗 6 个采样点全部通过。

全量 pytest 最终复跑：`253 passed, 1 warning in 26.08s`。严格门禁最终复跑：`FAIL 0 · WARN 1`，唯一 WARN 是 `dashboard_v2.html` 并存模板。

## 事实

### 分支、提交与门禁

- 当前 HEAD：`42e30e8`，48 files changed，`2461 insertions(+), 33 deletions(-)`。
- r01 中写的 `2463 insertions` 是统计笔误，以 `git show --stat 42e30e8` 的 `2461` 为准。
- 最终 `git diff --check`：退出码 0。
- 最终工作树在复制本回执前干净；本回执及原始证据是本轮新增未跟踪文档。
- stash 均保留，未 drop：
  - `stash@{0}`：`native-notify-and-build-script-for-step9`
  - `stash@{1}`：`ENG-20261124-01: preserve WAL repair before dashboard SPEC`

### 第 8 步前置与快照

- 只读钥匙串预检：`Vault.macos_existing()` 成功；未调用 `set_password`、未新建/修改/删除/导出钥匙串项。
- 停服前 8765：PID `22668`，`version=0.5.0`，`backup_error=null`，`reminder_error=null`。
- 2026-11-25 15:24:06 停止 PID `22668`，1 秒内退出，8765 释放，数据库无持有进程。
- `PRAGMA wal_checkpoint(TRUNCATE)` 返回 `0|0|0`。
- 新快照：`/Users/dkai2024163.com/ai/archive/jingxiaodian-leads-p1-20261125/pre-p1-cutover-final.db`
- 新快照 SHA-256：`68981d2fa8ff564b3a1d4cbbbce779400511dde6b1cb3f82fe633d1b7071fa64`
- `immutable=1` 校验：`integrity_check=ok`、`foreign_key_check` 无输出；候选 0、项目 0、审计 0、迁移头 `20261124_marketing_fields`。
- 快照权限：归档目录 `700`，快照 `600`；无 `-wal` / `-shm` 附属文件。
- 旧 0.3.0 回滚基线未覆盖、未改名、未删除，现场 SHA-256 复核为 `1309e1c2fb1eab358296483aae9f048ba339dc246da06d87ded774cf6435e9b8`。
- 代码回滚快照：`/Users/dkai2024163.com/ai/archive/jingxiaodian-leads-p1-20261125/code-5683098.tar.gz`，SHA-256 `fec85fdcd4c114316c00212bd3a74cacceb5971cf06272836cd19d4463af271f`；已解压到同目录 `code-5683098`，导入预演确认旧 GET 导出路由存在。

### 启动与部署修正

- 第一次启动 PID `11850` 在父会话结束后被回收，服务日志无应用异常；属启动方式未脱离父会话，不是代码启动失败。
- 第二次启动 PID `12509` 后发现正式 `.venv` 仍使用 11:54 安装的旧 site-packages 拷贝，源码改动未生效；GET 导出仍返回 200。
- 停止 PID `12509` 后执行：
  `/Users/dkai2024163.com/.local/bin/uv pip install --python .../.venv/bin/python --no-deps -e .`
- 修正后 `.venv` 为 editable：`Editable project location: /Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05`，导入路径为 `src/jxd_leads/__init__.py`。
- 最终服务 PID `13511`，独立 session 启动，启动后 3.1 秒 `/health` 就绪，2 秒后仍存活。

### 切换验收

- `/health`：`app=JXD-LEADS-001`、`version=0.5.0`、`backup_error=null`、`reminder_error=null`、备份与提醒时间均存在。
- 8 页：`/`、`/dashboard-v2`、`/candidates`、`/projects`、`/research`、`/insights`、`/import`、`/settings` 全部 200。
- MCP：`schema_version=1.3`、`version=0.5.0`、18 个工具，工具名与 capabilities 一致。
- 迁移头：`20261124_marketing_fields`，未新增表、未改迁移头。
- 导出边界：
  - `GET /exports/projects.csv` → `405`
  - `POST /exports/projects.csv` 无 CSRF → 页面提示“会话已失效，请刷新页面重试”
  - `POST` 带 CSRF → `200`，返回 `attachment; filename="jxd-projects.csv"`
  - `_audit` 新增 1 条：`owner|export.csv|projects|0 行`
- 导出验证只在空候选/空项目库上执行，没有导出真实客户数据；新增审计记录是预期写入。
- 10 分钟观察：0/2/4/6/8/10 分钟共 6 个采样点，health、MCP、PID `13511` 和 8765 监听均正常；服务日志未命中 `KEY_UNAVAILABLE`、`database is locked/busy`、`lock timeout`、`503 Service Unavailable`、`Traceback`。

### 测试与并发

- 全量 pytest 最终复跑：`253 passed, 1 warning in 26.08s`，测试 venv 为 `/Users/dkai2024163.com/WorkBuddy/2026-11-25-10-38-06/.venv-p1-tests/bin/python`，pytest `9.2.0`，Python `3.12.11`。
- 第 5 步真实 MCP + Web 同临时库并发 10 轮：`web_503=0`、`lock_timeouts=0`、`mcp_failures=0`、`web_failures=0`、`max_ms=20.1`、`candidate_rows=20`。
- 判断：暂不增加单实例锁；触发条件为出现第二个使用者或并发实测失败。该监控项保留。

## 判断

- 第 8 步最终状态为通过；切换后运行的是 v05 `src` 中的新代码，不是旧 site-packages 拷贝。
- 首次启动被父会话回收、第二次启动命中旧包，都是切换前置问题；修正后没有再次重启，当前服务已在观察窗内稳定运行。
- 新快照是本轮 0.5.0 代码回滚的数据基线；旧 `1309e1c2…` 仍是 0.3.0 归档基线，两者不能混用。
- 本轮没有新增第 19 个工具，没有改数据库迁移头，没有新增表，没有执行 `rm`，没有写钥匙串。

## 回滚路径

- 若最终服务需要回退且数据库未损坏：停 PID `13511`，用 `code-5683098` 代码快照启动旧行为，数据继续使用当前库；旧行为 GET 导出已通过导入预演确认。
- 若当前库需要恢复：先停服务，再用 `pre-p1-cutover-final.db`（SHA `68981d2f…`）恢复到隔离目标，核对完整性和迁移头后再决定是否覆盖；不得直接用旧 `1309…` 覆盖当前 0.5.0 库。
- 若钥匙串返回 `KEY_UNAVAILABLE`：停在停服前，报告并等待决策；不自动第三次重试，不生成替代密钥。
- 本轮未实际执行回滚；仅完成新快照、旧基线复核和回滚代码导入预演。

## 产物索引

原始证据目录：`/Users/dkai2024163.com/WorkBuddy/2026-11-25-10-38-06/20261125-B-P1-step8/`

| 文件 | 内容 |
|---|---|
| `20261125-p1-step8-preflight.txt` | 停服前 PID、health、库计数、旧基线哈希、钥匙串只读预检 |
| `20261125-p1-step8-stop-freeze.txt` | 停服、端口释放、checkpoint |
| `20261125-p1-step8-snapshot.sha256` | 新快照 SHA-256 |
| `20261125-p1-step8-snapshot-check.txt` | `immutable=1` 完整性与计数 |
| `20261125-p1-step8-editable-install.txt` | 正式 `.venv` editable 安装与导入路径 |
| `20261125-p1-step8-health.json` | 切换后 `/health` 原始回执 |
| `20261125-p1-step8-pages.txt` | 8 页状态码 |
| `20261125-p1-step8-mcp.json` | 18 工具与 capabilities 原始回执 |
| `20261125-p1-step8-export-check.txt` | GET/POST/CSRF/审计结果 |
| `20261125-p1-step8-observation.jsonl` | 10 分钟观察原始记录 |
| `20261125-p1-step8-final-check.txt` | 最终 PID、hash、库计数、git 状态 |
| `20261125-p1-step8-final-pytest.txt` | 最终全量 pytest |
| `20261125-p1-step8-final-preflight.txt` | 最终严格门禁 `FAIL 0 · WARN 1` |
| `20261125-p1-step8-rollback-import.txt` | 回滚代码快照导入预演 |
| `20261125-p1-step8-scope-grep.txt` | 旧口径 `NO_OLD_SCOPE_HITS` 与五类场景/三级地区命中 |

逐步 diff 仍以 `20261125-p1-step1.diff` 至 `20261125-p1-step9.diff` 及 `20261125-p1-all.diff` 为准；第 8 步没有代码 diff，只有部署与运行状态变化。
