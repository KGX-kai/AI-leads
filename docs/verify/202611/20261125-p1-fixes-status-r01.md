# 第三步 B · P1 修复状态回执 r01

日期：2026-11-25
工作目录：`/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05`
分支：`p1-fixes-20261125`
当前提交：以 `git log -1` 为准（提交信息 `feat(p1): enforce six-day window, csv audit, idempotency and suppress guards`）
状态：第 1–6、9 步代码与分步测试完成；第 7 步全量 pytest 通过，提交后严格门禁 FAIL 0 / WARN 1；第 8 步未执行；8765 未重启。

## 1. 事实

### 第 0 步｜基线与 stash

- 第 0 步提交：`5683098 docs(scope): land r01/r02 taxonomy and preflight receipt`
- 具名 stash：`native-notify-and-build-script-for-step9`
- stash 对象：`40cd4194301162cd49fb1bba1f5f0e7d2b5d1459`
- stash 内容：`native/notifications/main.swift`、`scripts/build-notifications.py`
- 第 0 步复跑门禁：FAIL 0 / WARN 2；输出见 `20261125-p1-fixes-preflight.txt`

### 第 1 步｜公告六日窗口

- `schemas.py` 的 `source_type` 新增 `公开招标公告`，保留旧值。
- `service.py` 对 `source_type=公开招标公告` 且 `published_at` 早于北京时间当日前第六日的候选跳过，不写候选表，note 记录跳过数量与原因。
- 机构电话校验对 `公开网络` 和 `公开招标公告` 两种公开类型放行。
- `overview` 与 `dashboard_snapshot` 的来源统计均加入公告类型。
- `dashboard_model.SOURCE_TONES` 新增 `公开招标公告: orange`。
- 测试：`tests/test_core.py` 9 passed，覆盖 45 天公告跳过、5 天公告入库、45 天官网入库、六日边界、机构电话和两处统计。
- 证据：`20261125-p1-step1-pytest.txt`、`20261125-p1-step1.diff`

### 第 2 步｜CSV 导出边界

- `/exports/{kind}.csv` 从 GET 改为 POST，复用现有 CSRF 表单校验。
- 导出类型白名单：`inquiry-template`、`inquiries`、`template`、`projects`、`candidates`。
- 每次成功导出写入 `Audit(action="export.csv", entity_id=kind)`。
- 所有导出入口模板改为 POST 表单；新增 `.inline-action` 样式。
- `projects` / `candidates` 保留公司、地址、来源链接明文，供本人查阅并可追溯；`inquiries` 继续使用现有脱敏结果。
- 测试：`tests/test_safety.py` 23 passed；模板回归 42 passed。
- 证据：`20261125-p1-step2-pytest.txt`、`20261125-p1-step2-templates.txt`、`20261125-p1-step2.diff`

### 第 3 步｜submit_candidates request_id

- `mcp_server.submit_candidates` 增加 `request_id: str = ""`。
- `Service.submit_candidates` 非空 `request_id` 走 `execute_once`，同编号同内容返回原结果，同编号异内容返回 `IDEMPOTENCY_CONFLICT`。
- 重放不覆盖 `research.status/note`。
- 测试：11 passed。
- 证据：`20261125-p1-step3-pytest.txt`、`20261125-p1-step3.diff`

### 第 4 步｜add_contact / update_offer

- `add_contact` 统一走 `_allowed(s, p, allow_blocked_contact=True)`：合并项目返回 `VERSION_CONFLICT`，停联项目返回 `SUPPRESSED`；已拒绝联系人仍可被记录为 blocked，保留现有行为。
- `update_offer` 走 `_allowed(s, p)`；终态 `已采购/未接受` 关闭 `add_offer` 建立的同名关联 Todo；使用机会 `version` 做乐观锁，成功后递增机会和项目版本。
- 网页报价表单传入隐藏 `version`。
- 测试：16 passed，覆盖停联/合并拒绝、终态关闭 Todo、版本不匹配。
- 证据：`20261125-p1-step4-pytest.txt`、`20261125-p1-step4.diff`

### 第 5 步｜并发实测

- 临时新库、内存 Vault、真实 MCP stdio 子进程 + 本地 Web 端口 8799，10 轮并发写。
- 结果：`web_503=0`、`lock_timeouts=0`、`mcp_failures=0`、`web_failures=0`、`max_ms=20.1`、`candidate_rows=20`。
- 判断：实测无并发问题，暂不加实例锁；触发条件=出现第二个使用者或实测失败；列入监控项。
- 原始数据：`20261125-p1-step5-concurrency.json`；摘要：`20261125-p1-step5-summary.txt`

### 第 6 步｜propose_tag 调研

- `TOOL_NAMES` 仍为 18 个，未新增第 19 个工具。
- `list_tags` 可用；`add_tag` 要求 owner；Agent 当前不需要独立建标签。
- 结论与触发条件：`20261125-p1-step6-propose-tag.md`

### 第 9 步｜技术债

- `desktop.py` 支持 `JXD_NOTIFICATION_HELPER`；启动器显式指向 v05 真实 helper。
- `.venv` 内软链已移动到 `/tmp/jxd-p1-symlink-backup/JXDNotifications.app`，未 `rm`；默认路径仍可解析到真实文件。
- 启动器端口改为 `JXD_PORT`，默认 8765。
- `native/notifications/main.swift` 与 `scripts/build-notifications.py` 纳入 git；`runtime/` 继续不入库；已写入 `docs/INTERNAL-directory-map.md`。
- 版本号统一由 `importlib.metadata.version("jxd-leads")` 生成 `__version__`，`web.py` 与 `workflows.capabilities` 引用同一来源。
- 定向测试：17 passed。
- 证据：`20261125-p1-step9-tech-debt.md`、`20261125-p1-step9-version-pytest.txt`、`20261125-p1-step9.diff`

### 第 7 步｜统一回归

- 全量 pytest：`253 passed, 1 warning in 26.64s`。
- `git diff --check`：`DIFF_CHECK_EXIT=0`，无空白符错误。
- 提交信息：`feat(p1): enforce six-day window, csv audit, idempotency and suppress guards`
  48 files changed, 2463 insertions(+), 33 deletions(-)；提交后工作树干净。
- 提交前严格门禁：`FAIL 1 · WARN 1`，唯一 FAIL 为 48 个文件未提交。
- 提交后严格门禁：`FAIL 0 · WARN 1`，工作树干净，基线提交 `8bd1322`。
- WARN：`src/jxd_leads/templates/dashboard_v2.html` 为并存版本模板；`web.py` 手写版本 WARN 已消失。
- 证据：`20261125-p1-step7-full-pytest.txt`、`20261125-p1-step7-preflight.txt`、`20261125-p1-step7-preflight-final.txt`；提交后门禁原始输出保存在 WorkBuddy `20261125-B-P1-fixes/`。

### 8765 现场状态

- PID 22668 仍在运行，未重启。
- `/health` 返回 `version=0.5.0`，`backup_error=null`，`reminder_error=null`。
- 旧回滚快照 `pre-cutover-final.db` 现场 SHA-256 复核为 `1309e1c2fb1eab358296483aae9f048ba339dc246da06d87ded774cf6435e9b8`，与给定基线一致。
- 本施工包未执行第 8 步，未生成新快照，因此没有新快照 SHA。

## 2. 判断与下一步

第 7 步已通过：全量 pytest 253 passed，提交后严格门禁 FAIL 0 / WARN 1，工作树干净。WARN 仅为 `dashboard_v2.html` 并存版本模板，符合 WARN ≤2 要求。

第 8 步尚未执行。下一步按施工包流程做钥匙串只读预检、冻结并生成新快照、停服切换、验收和 10 分钟观察；失败按回滚决策树恢复，不用 `--allow-dirty` 绕过。

## 3. 产物索引

| 文件 | 用途 |
|---|---|
| `20261125-p1-all.diff` | 最终工作树完整 diff（不含未跟踪文件内容） |
| `20261125-p1-step1.diff` | 第 1 步中间态 diff |
| `20261125-p1-step2.diff` | 第 2 步相关文件最终 diff（`web.py` 含第 4 步字段） |
| `20261125-p1-step3.diff` | 第 3 步相关文件最终 diff（`service.py` 为跨步最终态） |
| `20261125-p1-step4.diff` | 第 4 步相关文件最终 diff |
| `20261125-p1-step9.diff` | 第 9 步桌面通知与版本来源 diff |
| `20261125-p1-excluded-files.sha256` | 启动器、目录地图、SPEC 的 SHA-256 |
| `20261125-p1-git-status.txt` | 当前 `git status --short` |
| `20261125-p1-step7-preflight-final.txt` | 加入回执后的门禁最终复跑输出 |
| `20261125-p1-step5-summary.txt` | 并发实测摘要 |
| `20261125-p1-step6-propose-tag.md` | propose_tag 调研结论 |
| `20261125-p1-step9-tech-debt.md` | 技术债处理回执 |
| `20261125-scope-grep-final.txt` | 第三步 A 旧口径最终 grep（未命中） |

工作空间同步副本：`/Users/dkai2024163.com/WorkBuddy/2026-11-25-10-38-06/20261125-B-P1-fixes/`

## 4. 未执行

- 第 8 步：钥匙串只读预检、冻结、新快照、停服切换、8 页/18 工具/迁移头验收、10 分钟观察。
- 新快照 SHA、切换回执、回滚决策树执行记录。
