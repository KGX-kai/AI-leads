# 🧩 SPEC-20261124 · 0.4.0 看板聚合

状态: active
base_commit: 1b12d4258b116c7e152f77bf7e3945669b1bada9
任务: ENG-20261124-01
规格修订: r02（r01 正文与确认记录保留；r02 新增第 11、12 节）
确认状态: r01 已于 2026-11-24 确认并完成隔离验收；r02 已于 2026-11-24 由本人确认：五项全做并升 0.5.0；渠道初始列表用方案 5.5 的 8 个来源；停滞阈值 EMC 30 / 买断 7 / 未定 14 天。
设计输入: v0.4.0 / rev-f47cfd6a90e5；主题包 rev-9b78fa9d5d99（SHA-256 1fbcf876…6d23d9，取代此前两个包）
需求输入: work/ENG-20261124-01-marketing-extract-r01.md（营销方案 v1，SHA-256 346834e0…df9ab）

## 1. 基线

目标仓库由 `JXD_ISOLATED_ROOT` 指定。下列命令中的 `PREFLIGHT_SCRIPT` 指向本机门禁脚本，`JXD_OUTPUT_DIR` 指向聚合包输出目录。

| 项 | 本轮核对结果 |
|---|---|
| 起点 | `main`，HEAD 为本文件的 `base_commit` |
| 当前分支 | 已从上述 `main` 创建 `feat/dashboard-v0.4.0`，HEAD 未变 |
| 保护标签 | `v0.4.0-candidate.1`，注释标签对象 `8f1c24fe10702058a4f6c6e2bef5867e8b7c843b` |
| 标签所指代码提交 | `5bd89e21d465a1a2bc25a1b337be440ba02b76e5`；不得移动、覆盖或重建标签 |
| 版本与契约 | 候选 0.4.0；18 个受限 MCP 工具；回执 schema 1.2；stdin 仍为 `{"tool":...,"arguments":{...}}` |
| 原有未提交改动 | 4 个修改文件及 2 份未跟踪证据，已单独存入 Git stash，6 项内容哈希全部一致 |
| 保全点 | `fd3945a2c4e61c457c611e595341d4577026f1ca`，说明 `ENG-20261124-01: preserve WAL repair before dashboard SPEC` |
| 清理后的门禁 | 使用现有工程 Python 3.12.14，`FAIL 0 / WARN 5`；这是生成本 SPEC 前的干净基线检查 |
| 本轮实际操作 | 只读审查、哈希验证、stash、建分支及规划/证据文档；未聚合实现、测试运行、构建、启服务或操作数据库 |

输入 ZIP：
`${JXD_OUTPUT_DIR}/京小电获客工作台-v0.4.0-聚合包-20261124/京小电获客工作台-v0.4.0-聚合包-20261124-rev-f47cfd6a90e5.zip`

- ZIP SHA-256：`7e9cc411d3e6801fb85a12107ae4ead21736cf501020d869b665293860294673`。
- 已先读包内 `AGGREGATION.md`、`GO-LIVE.md`；CRC、路径安全、MANIFEST 中 10 项哈希、SHA256SUMS 中 6 项哈希均通过，设计修订一致。
- 包内 `tag_commit` 实际是注释标签对象，不能与代码提交混为一谈。本规格分别记录二者。
- 0.3.0 从未正式使用、没有待迁移的业务数据，采用用户最新决定：上线启用全新 0.4.0 数据目录，旧目录保留不删。本轮不需要为旧业务库做迁移或备份。
- 现有主控旧表格中的“等待看板路径”“必须先建 0.3.0 首提交”“9 个资源必然漏包”已不适合作为本轮前提；候选配置已包含 `static/dashboard/*`，实际发行物仍待验。

### 原有 WAL 修复的处理

stash 包含 `CHANGELOG.md`、`src/jxd_leads/backup.py`、`src/jxd_leads/security.py`、`tests/test_data_contract.py`，以及旧验证输出和其索引。内容是防止校验自包含 WAL 备份时生成 sidecar 的修复，应保留。

该修复已按本规格恢复、复跑并独立提交为 `ca0e4d9f549cb0708474e1518672d011d4de5e79`；stash 仍保留到最终验收。旧证据中的 `216 passed` 是历史结果，本轮新跑的 216 passed 独立记录在新证据中。

恢复时保留 stash，按上述固定 SHA 提取 4 个修改文件和旧证据；将旧索引条目合并到本轮索引，不直接覆盖 `docs/verify/INDEX.md`，不盲目 `stash pop`。修复及证据收口前不删除保全点。

## 2. 目标

将获批设计修订接入已有 0.4.0 功能，使单人使用者能在看板读取真实记录、核对统计与状态，并通过现有业务页面完成审核或跟进。保留设计布局、视觉令牌、字体、头像和响应式效果；空库不显示演示业绩。

聚合在现有候选仓库内完成。正式上线、正式数据目录的最终路径和启用时间另行批准。

## 3. 非目标

- 不切换正式服务，不改旧 0.3.0 工程，不迁移、读取或删除旧客户数据库及旧目录。
- 不改 MCP 工具数量/名称、回执格式、stdin 协议、既有 ID、停联规则和人工审核权限。
- 不修改看板设计源工程；不重新设计主题、重做布局或批量改写其他业务页面。
- 不新增自动联系、渠道采集、发送、平台权限、团队协作、AI 一键采纳或真实业务试点。
- 不虚构渠道历史趋势、报告文件、跟进时间线、增长率、响应时间、联系人或备份成功状态。
- 不新增运行依赖；不把浏览器/代码测试、备用 MCP 或健康检查当作 WorkBuddy 原生及真实渠道验收。
- 不读取、导出或另存钥匙串、凭证、Cookie；本轮隔离测试使用合成临时库和临时密钥。

## 4. 建议接入范围与受影响文件

首轮建议采用“完整只读看板，写动作进入现有业务页面”。它保留已实现功能的审核与持久化行为，避免演示脚本在内存中改状态后假报成功。

| 范围 | 文件及预期变化 |
|---|---|
| 页面与资源 | 替换 `src/jxd_leads/templates/dashboard_v2.html`；新增 `src/jxd_leads/static/dashboard_v2.css`、`dashboard_v2.js` |
| 数据映射 | 新增 `src/jxd_leads/dashboard_model.py`，纯函数 `build_dashboard_model` 只转换传入数据，不直接打开数据库或调用写接口 |
| 网页接线 | `src/jxd_leads/web.py` 接 boot、查询条件及必要的网页专用只读数据路由；优先复用现有 Service 读方法 |
| 回归 | 扩展 `tests/test_dashboard.py`，必要时拆为独立 adapter/安装验证测试；复用现有临时数据库夹具 |
| 设计参考 | 按包内映射保存 `docs/dashboard-tokens-v0.4.0.json`、`dashboard-view-model-v0.4.0.json`、`dashboard-overview-v0.4.0.json`、`dashboard-spec-v0.4.0.md` |
| 发布包 | 验证模板、全部静态资源及迁移资源；若独立安装探针确认缺失，最小修改 `pyproject.toml`、迁移资源打包/定位和相关测试，不改变迁移 revision 或数据库结构 |
| 基线卫生及收口 | 独立恢复 WAL 修复；补必要的忽略规则/门禁钩子；更新候选 `CHANGELOG.md`、本 SPEC、验证输出和索引；只同步主控相关状态与来源 |

`dashboard_v2.html` 作为独立整页，不继承 `base.html`。移除设计基线 `system` 视图后保留其余 9 个业务视图。旧 `/` 首页暂时保持，聚合入口为 `/dashboard-v2`；正式切换时再确认默认入口，不另建 `_v3` 模板。

不预先承诺需要修改 Service/Workflows。如果现有查询无法满足真实分页、停联展示或字段安全，只增加网页所需的最小只读方法，记录影响，保持原有快照与 MCP 语义。

## 5. 数据与交互约定

### 读模型

| 模块 | 数据与范围 |
|---|---|
| 总览 KPI / 漏斗 | 使用 `dashboard_snapshot()` 原口径；第二级实际是“已建档”，不能改称“已联系”；零分母显示空态或“—”，不能把首行固定 100% 当成成交或转化 |
| 新增趋势 | 使用现有 `trend["8w"]` / `trend["6m"]`；标为每周/每月新增，不误称累计；服务端北京时间决定日期 |
| 来源构成 | 两个圆环消费实际 `sources`；无数据时显示空态 |
| 渠道时间趋势 | 当前快照没有历史渠道序列，显示“暂无历史序列”，不从当前总量生成历史 |
| `leads` | 使用 `list_candidates` 的真实分页、筛选及总数，保留原 ID/状态；不能把快照的最近 6 条冒充全部线索 |
| `projects` | 使用已有项目查询，排除合并项；分页或筛选范围明确，不受总览最近 6 条限制 |
| `opportunities` | 使用现有只读机会查询，排除 historical；保留暂缓、关闭、停联及关联 ID，不推断需求或采购事实 |
| `tasks` | 使用 `today_queue` 完整待处理队列（不传 `kind`），涵盖逾期/未来待办，以及停联、咨询、候选和待审建议；不局限总览 8 条。超过 100 条时显示已加载数并进入完整分页页 |
| `reports` | 没有报告对象则 `[]`；可独立展示 `quality` 的当前 30 日摘要，不能制造已生成报告 |
| `notifications` | 复用已有通知查询，注明最多最近 100 条；总览最近 5 条与完整通知页面有清晰入口 |

列表字段采用白名单与已有脱敏输出，不为看板额外读取/解密联系人或跟进密文。项目阶段、机会阶段和候选审核状态分开；未知状态保留原值/待核实，不强行映射成新线索。

### 演示行为替换

- 清理全部可达视图、抽屉、工具提示、ARIA 文本、日期与摘要中的演示数据，包括硬编码时间线、AI 草稿、备份状态与最近活动。
- `overviewData` 和 `channelData` 与列表脚本位于不同闭包，不能跨作用域直接读 `DEMO`。统一规范化服务端注入的对象，两处使用同一真实模型；缺少注入时只产生空态。
- 删除演示数组、设计基线入口/section、`example-tag`、`state-preview` 和示例页脚。示例 JSON 仅保留为文档，不作为运行数据回退。
- 跟进、阶段推进、人工审核、导入、通知已读和备份操作链接到已有 `/candidates/{id}`、`/projects/{id}`、`/opportunities/{id}`、`/reviews`、`/import`、`/notifications`、`/settings` 等对应入口。
- 没有对应能力的团队设置、批量分配、报告生成或 AI 采纳明确禁用/说明，不弹“已保存”“已发送”等虚假回执。支持的导出沿用既有端点并注明范围。
- `boot | tojson` 保留，不用 `safe`；所有来自记录的文本、HTML 属性、外链和 class 值采用安全渲染/允许值校验，恶意文本必须显示为文本。

## 6. 契约变化

| 层 | 约束 |
|---|---|
| 网页 | 新增看板内部读模型与必要只读查询，页面显示真实状态；交互从演示动作改为现有业务页入口 |
| MCP / 备用脚本 | 18 工具、schema 1.2、stdin 的 `tool/arguments`、退出码保持；本轮不改受限接口 |
| 数据库 | 无新增业务字段、表或迁移 revision；现有 ID、停联与批准状态保持 |
| 运行 | 验收用临时目录/独立 8877；正式双目录参数配置仅在后续获批切换时变更 |
| 版本 | 保持 0.4.0 候选，纯 UI/只读显示改动在 CHANGELOG 明记“不影响 MCP 契约”；若需突破以上边界，先更新规格与契约确认 |

## 7. 验收标准

以下为 2026-11-24 的实现验收结果。勾选项均有 `docs/verify/202611/` 中的新输出；未验项继续列在证据文件，不以测试通过代替正式上线。

- [x] **基线**：固定标签对象及所指提交未变；WAL 修复独立提交；实施提交为 `24c70f9`；干净工作树上 `preflight.py . --strict` 为 `FAIL 0 / WARN 2`。
- [x] **映射**：合成夹具覆盖空库、缺日期/字段、25 条候选分页、105 条任务截断、停联/暂缓/关闭、原 ID 和真实详情链接。
- [x] **真实性**：六列表、四图表及漏斗空态正确，无示例公司、假业绩、固定历史时间线、`undefined` 或 `NaN`；零值与未知区分。
- [x] **交互**：记录链接命中对应 ID；完整列表入口不受总览限额影响；写动作进入既有页面，刷新不出现内存假保存；停联/待审状态不因前端操作被改写。
- [x] **浏览器**：真实 standalone 与精确宽度容器已验；1440/390 均无页面级横向溢出，搜索面板可见、可过滤、Escape 关闭。真实文件报错捕获器未发现错误；srcdoc 容器自身的 `replaceState` 限制已单独记录，DevTools Console 导出和截图为未验项。
- [x] **注入安全**：含引号、HTML、`</script>` 和危险 URL 的合成记录不执行脚本、不产生异常导航；候选签名 URL 与解密建议不进入看板，页面不增加联系人明文暴露。
- [x] **回归**：全量 pytest `228 passed`，看板聚焦 `14 passed`，MCP 聚焦 `13 passed`，ruff、JS 语法和 diff 检查通过。
- [x] **发行物**：最新 wheel SHA-256 为 `f7e0f560…ca4b2e`；模板、CSS/JS、14 项静态资源及迁移资源齐全，36/36 个模板/静态文件哈希与工作树一致。
- [x] **独立安装**：新 venv 中安装 wheel，源码路径未进入 `sys.path`；空库迁移到 `20261117_candidate_quality`，health、看板和 14/14 静态资源均返回 200。
- [x] **数据隔离**：合成运行使用 `Vault.ephemeral()`；未访问系统钥匙串或正式数据目录。
- [x] **证据**：命令、退出码、提交、浏览器尺寸、wheel 哈希、资源清单和未验项已写入 `docs/verify/202611/` 并登记索引。

正式服务、真实 TCP、系统钥匙串、生产启动器、WorkBuddy 原生联调和真实业务试点仍未验收，不能因本节通过而宣布正式上线。

现有解释器及聚焦验证命令（恢复 WAL 修复后执行）：

```zsh
cd "${JXD_ISOLATED_ROOT}"
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_data_contract.py -k 'verify_wal_database or same_day_backup_with_live_wal or default_backup_repairs or backup_verification'
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard.py
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m ruff check --no-cache src tests scripts
.venv/bin/python "${PREFLIGHT_SCRIPT}" . --strict
git diff --check
```

本轮查到现有解释器缺 `setuptools`、`build`、`wheel`。下面仅是待批准的临时构建工具准备，不改现有环境或运行依赖；不在本轮执行：

```zsh
cd "${JXD_ISOLATED_ROOT}"
JXD_BUILD_ROOT="$(mktemp -d /tmp/jxd-dashboard-build.XXXXXX)"
.venv/bin/python -m venv "$JXD_BUILD_ROOT/build-venv"
"$JXD_BUILD_ROOT/build-venv/bin/python" -m pip install 'setuptools>=75' build wheel
"$JXD_BUILD_ROOT/build-venv/bin/python" -m build --wheel --no-isolation --outdir dist
.venv/bin/python -m venv "$JXD_BUILD_ROOT/verify-venv"
"$JXD_BUILD_ROOT/verify-venv/bin/python" -m pip install ./dist/jxd_leads-0.4.0-*.whl
```

独立安装探针须在临时验证工作目录运行，显式清除 `PYTHONPATH`，记录加载位置；临时验证脚本可以调用已安装包的 Database/Service 与临时 Vault，不得把源码预览脚本的 `sys.path.insert` 当作安装验收。生成探针和细化命令属于确认后的验证任务。

## 8. 我的假设与待确认项

1. **推荐范围｜已确认**：首轮按第 4–5 节做真实只读看板；可用写操作进入已有业务页。渠道历史、报告生成、团队能力等缺项保留明确空态/不可用说明，不在本轮扩成新业务功能。
2. **本地提交｜已确认**：恢复现有 WAL 修复并独立本地提交，随后按小切片提交规划、看板实现和验收证据；不推送、不发布、不改保护标签。不执行未经批准的 Git 历史重写。
3. **构建工具｜已确认**：仅在临时环境补齐上述构建工具和安装项目已声明依赖，不新增产品运行依赖；下载/安装失败如实报告，不能跳过独立安装验收。

上述三项已由本人于 2026-11-24 一次确认。正式目录最终路径、默认首页切换、切换时点与真实业务仍另行确认；本人明确还有两项待补充需求，将在聚合完成后统一确认上线，本轮不自动切换。

## 9. 确认后的拆分规则

按门禁步骤 6，确认本规格后再生成实施任务：每个任务最多 5 个文件、带 Verify 命令，每 2–3 项设置一个检查点。优先恢复并收口既有修复，再做读模型/页面、浏览器与发行物验收。证据与索引纳入任务范围，不为凑文件数省略验证。

本轮不写实现代码，不提前勾选实施或测试通过。

## 10. 回退与退出条件

- **规划回退点**：`main@1b12d4258b116c7e152f77bf7e3945669b1bada9` 加上述固定 stash；本分支未改 `main`，保护标签不动。
- **实现回退点**：WAL 修复独立收口后的实际 commit，实施前记录；后续按具体提交撤销看板改动，不用 `reset --hard` 丢弃工作。
- **上线失败处理**：聚合回退到已核验的 0.4.0 代码与同一新数据目录；如果后续明确选择回到 0.3.0，只使用保留的 0.3.0 工程与旧目录。不能把 0.4.0 候选标签当成 0.3.0 回退代码，也不能让旧代码打开新库。
- 包内 GO-LIVE 的直接 `serve` 命令会使用系统钥匙串；它是后续获批上线参考，不是本轮自动执行授权。
- 候选旧 `/dashboard-v2` 占位模板在本次聚合验收通过时由新模板取代；旧 `/` 在正式切换批准前保留。
- 分支复核期限建议为 2026-11-27；届时未完成则报告剩余项，由用户决定继续，不自动切换、归档或删除。
- **本轮退出**：SPEC、基线及包核查证据可审阅，停在用户确认点；这只完成规划准备，不表示聚合完成。
- **聚合完成**：第 7 节全部通过、证据落盘、本地提交可追溯、遗留能力单列。正式上线仍需另行批准。

本轮规划证据：`docs/verify/202611/20261124-ENG-20261124-01-plan-r01.txt`。
后续实现证据：`docs/verify/202611/20261124-ENG-20261124-01-implementation-r01.txt`（未创建、未执行）。

---

## 11. r02 · 深浅色主题（不改契约）

来源：主题包 `rev-9b78fa9d5d99`，17 文件 `shasum -c` 通过；`styles.css`、`app.js` 与已接入版本一致，新增 `theme-light.css`、`theme.js`、主题令牌与 QA 清单。

| 项 | 做法 |
|---|---|
| 静态文件 | 新增 `static/theme-light.css`、`static/theme.js`；包内令牌、THEME-SPEC、QA 清单放 `docs/` 作参考 |
| 首屏防闪烁 | 包内 `<head>` 内联脚本会被现有 CSP `script-src 'self'` 拦截。改为同步加载的 `static/theme-init.js`，不放宽 CSP |
| 类名对齐 | 浅色覆盖 107 个类名中 4 个在接真实数据时已改结构：`lead-table`、`lead-meta`、`funnel-meta`、`section-title`，映射到现有类名 |
| 默认 | 深色；`localStorage["jxd-theme"]`；跨标签同步 |
| 缺件 | THEME-SPEC 提到的 `PATCH.md` 包内没有；按 AGGREGATION.md §3 接入，不影响施工 |

## 12. r02 · 营销方案需求（改契约，升 0.5.0）

完整对照见需求输入文件。23 个模块中本轮只取 5 项；其余已有、转其他项目或暂缓，理由记录在提炼稿第 2 节。

### R12-01 机会商务画像
- 来源：营销方案 M1、5.2、M11
- 改什么：机会/项目需求增 `business_mode`（EMC / 买断 / 两种都要 / 未定）、`annual_power_cost`（≥30万 / 5–30万 / <5万 / 未知）、`managed_projects`（整数或空）；咨询字段建议由 7 项增到 8 项（加电费区间）；看板与详情显示
- 保留什么：现有 ID、需求五项、确认规则、停联
- 契约影响：`get_opportunity_context` 返回新增项；`propose_opportunity_update`、`propose_inquiry_fields` 接受新增项（可选）
- 通过条件：不传新字段的旧调用结果不变；AI 只能建议，写入仍经本人审核
- 状态：已确认

### R12-02 来源渠道
- 来源：M3、M20 前置
- 改什么：候选与咨询增可选 `source_channel`；渠道列表存设置项，由本人在设置页增删，代码与默认值不写死渠道名；看板按渠道统计候选、咨询、机会数
- 契约影响：`submit_candidates` 增可选字段；`get_capabilities` 返回当前渠道列表；传入不在列表中的值返回 `VALIDATION_ERROR`
- 通过条件：空列表时字段可留空；统计与列表一致
- 状态：已确认

### R12-03 投标截止日
- 来源：方案 2.2（真实招标 2026-11-27 截止）、M14 规则②
- 改什么：候选增可选 `bid_deadline`（日期），晋升为机会时带入；`today_queue` 新增 kind `bid_deadline`，距截止 ≤7 天且未关闭时进入，已过期单独标注
- 契约影响：`submit_candidates` 增可选字段；`get_today_queue` 新增 kind 值
- 通过条件：截止日早于公告发布日拒收；与现有 7 天发布窗口规则并存
- 状态：已确认

### R12-04 阶段停滞预警与排除原因码
- 来源：M13、方案 1.5
- 改什么：按阶段进入时间算停留天数，超阈值在看板与待处理区标红；阈值按商务模式存设置项（建议 EMC 30 天、买断 7 天、未定 14 天）；候选排除原因码补「渠道商/批发」「同行询价」「合同期内」「需求过小」「无支付能力」
- 契约影响：无（只读展示与网页审核）；原因码新增值对 MCP 透明
- 状态：已确认

### R12-05 跟进节奏建议
- 来源：方案 5.4、M16
- 改什么：记录跟进时按商务模式和阶段给出建议下次日期，本人确认后才生成待办；不自动发送任何消息
- 契约影响：无
- 状态：已确认

### 明确不做
自动发送资料/私信/群发（M11、M14③、M15、M18）；内置节能率 60%、5 年质保等对外数字（M12）；代码内置「成都 + 物业」等地区场景默认值；温度评分、ROI、A/B、合同回款、转介绍（暂缓）。

### 版本与同步
- 版本：0.4.0 → **0.5.0**，schema 1.2 → **1.3**，新增迁移 revision；工具数保持 18；`agent-call.py` stdin `{"tool":...,"arguments":{...}}` 不变；回执五字段不变
- 理由：`v0.4.0-candidate.1` 已指向旧契约，同号会让 WorkBuddy 无法区分；0.4.0 未上线，跳号无用户成本。保护标签不动，另打标签需另批
- 同步：`pyproject.toml`、`/health`、`get_capabilities`、CHANGELOG、协作手册 r03（版本行、候选字段、交接格式、工具说明）、`workbuddy-v1.2.md` 标题
- 上线：全新 0.5.0 数据目录，不迁移旧库；GO-LIVE 中 0.4.0 字样改为 0.5.0

### r02 验收
- [x] 新迁移在空库与 0.4.0 合成库上可升级、可回退
- [x] 旧调用（不带新字段）MCP 回归全部通过；新字段正反例各有测试
- [x] 渠道、截止、停滞阈值均从设置读取，代码 grep 无业务地区/场景/渠道硬编码
- [x] 主题：十视图 × 1440/390 × 深浅，按 QA-CHECKLIST 截图落盘；无 CSP 报错
- [x] 全量 pytest、ruff、JS、门禁严格模式 FAIL 0（证据 candidate-r04；门禁结果记于提交后复核）
- [x] wheel 重建（0.5.0）并源码外安装验收；手册与 workbuddy 文档版本一致

### r02 确认记录（2026-11-24）
1. 五项全做并升 0.5.0｜已确认
2. 渠道初始列表用方案 5.5 的 8 个来源（招投标、物业协会、抖音同城、CABEP、展会、名单池、竞品客户、转介绍），作为设置数据初始化，可在设置页增删｜已确认
3. 停滞阈值 EMC 30 / 买断 7 / 未定 14 天，作为设置数据初始化｜已确认
