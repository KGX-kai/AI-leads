# 📝 第三步 A｜业务口径落盘回执

- 日期：2026-11-25
- 工作目录：`/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05`
- 任务：正式场景口径、飞书单向快照、旧库处置与路径更新落盘
- 状态：文档变更完成；未改 Python、配置、数据库；未动 8765
- 口径来源：本人 2026-11-25 拍板

## 1. 结论

正式口径已从“地区/场景待定、部分业态仅测试”改为“中国、逐次指定省市、按采购组织方式分 5 类”。`scene` 写一级分类，`tags` 写采购触发类型，不改表结构。飞书明确为工作台导出的脱敏只读下游，不是第二客户库。旧 0.3.0 库只读保留三个月，到期移废纸篓；回滚基线为 13:08 快照，SHA-256 已核对。

## 2. 改动清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/AGENTS.md` | 修改 | 工程路径改为 v05；状态源改为 v05 数据库；写入五类场景、`scene`/`tags`、六日窗口约束 |
| `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/operations.md` | 修改 | 新增“场景与字段口径”“飞书表格口径”“旧库处置与回滚基线”三节 |
| `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/workbuddy-v1.2.md` | 修改 | 路径改为 v05 与 `current/`；写入五类场景、`scene`/`tags` 写法、公告类六日窗口 |
| `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/README.md` | 新增 | 现行项目入口；不再保留旧单一地区、单一业态口径 |
| `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/INTERNAL-scene-taxonomy.md` | 新增 | 内部口径全文：五类、落库方式、触发类型、旧口径处置、变更控制 |
| `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md` | 修改（1 行） | 首段“不预设正式场景、物业/停车场照明仅测试”与新口径冲突，改为五类场景 + 养殖仅测试；其余章节未动 |

说明：v05 是阶段 A 从候选仓库复制的干净工程，原本没有 `AGENTS.md`、`operations.md`、`README.md`。按审查证据，旧表述位于主控 `AGENTS.md:8` 和主控 `operations.md:7`，因此这两处更新主控同名文件；v05 侧新建 `README.md`，避免把旧 0.3.0 的 README 口径带回来。

## 3. 逐处 diff

> 本节含删除行原文，仅用于留证。验证“旧表述已清除”时，grep 范围应排除本回执。

### 3.1 主控 `AGENTS.md`

```diff
--- /tmp/jxd-scope-r01/hub-AGENTS.before.md
+++ /Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/AGENTS.md
@@ -1,11 +1,11 @@
 # 🧭 统一主控执行规则
 
-本项目 JXD-LEADS-HUB-001 是协调与文件入口；唯一工程仍为 JXD-LEADS-001：/Users/dkai2024163.com/ai/product/jingxiaodian-leads。
+本项目 JXD-LEADS-HUB-001 是协调与文件入口；唯一工程为 JXD-LEADS-001：/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05。
 每次先读 context.md、progress.md（progress.md 只含当前状态与待办）；仅按任务读取 operations.md、maintenance.md、integrations.md 和 sources.json。不要全部历史重读；逐日流水在 history/progress-log-YYYY-MM.md，只在追溯某个具体日期/决定时打开，收口时追加到该流水文件，不写回 progress.md。
 当前文件优先于旧窗口，具体合同与用户较新明确指令优先于通用政策。冲突要保留依据，不能静默覆盖。
-业务记录只通过工作台受限接口提交建议；真实客户和机会的唯一状态源为原工程数据库，不在本项目建第二个客户库。
-工程任务进入原工程先读其 AGENTS.md、progress.md，检查 git status。未经明确授权不提交、推送、部署、发送或新增定时任务。
-正式业务地区和场景尚待本人逐次指定；养殖、物业、停车场照明均为测试场景，不作正式默认范围。单人本机。EMC知识可引用但不自动扩展获客范围。事实、建议、未知分开。
+业务记录只通过工作台受限接口提交建议；真实客户和机会的唯一状态源为 v05 工作台数据库（`/Users/dkai2024163.com/ai/data/jxd-leads/current/`），不在本项目或飞书建第二个客户库。
+工程任务进入 v05 先读 `docs/workbuddy-v1.2.md`、`docs/INTERNAL-scene-taxonomy.md` 和 `docs/plan/`，检查 git status。未经明确授权不提交、推送、部署、发送或新增定时任务。
+正式地区为中国，具体省市由本人逐次指定；正式场景按采购组织方式分 5 类：公共建筑（学校、医院）、商业地产（酒店、商业综合体）、居住社区（中大型物业小区）、工业与连锁（工厂、连锁商超/药店）、市政与公共空间（市政路灯、地下停车场）。`scene` 写一级分类，`tags` 写采购触发类型（新建扩建/存量改造/连锁展店/政策驱动/更换周期），不改表结构。地区+场景仍须本人逐次明确；六日窗口只对公告类生效。未列入五类的场景（如养殖）仅用于隔离测试，不作正式默认范围。单人本机。EMC知识可引用但不自动扩展获客范围。事实、建议、未知分开。
 所有业务输出默认待审；不代点人工审核，不承诺未经批准的报价、节能率、质保或履约能力。
 新任务文件用稳定任务编号和修订号，保留来源ID、已有客户ID、内容ID和批准状态。后续交付写本项目 outputs/；草稿写 work/。
 references 是2026-11-09证据快照，不自动代表未来最新版本；改业务口径前复核原来源。凭证、原始客户库不得复制到此。
 完成后只更新本项目相关状态和来源索引；不要自动更新全局记忆或恢复归档项目。
```

### 3.2 主控 `operations.md`

```diff
--- /tmp/jxd-scope-r01/hub-operations.before.md
+++ /Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/operations.md
@@ -2,13 +2,31 @@
 
 ## 日常顺序
 
-1. 读取原工程 docs/workbuddy-v1.2.md，调用 get_capabilities/get_today_queue，记录真实版本、连接方式、ok/error与权限。接口失败不直接读写SQLite绕过。
+1. 读取 v05 工程 docs/workbuddy-v1.2.md，调用 get_capabilities/get_today_queue，记录真实版本、连接方式、ok/error与权限。接口失败不直接读写SQLite绕过。
 2. 优先停联复核、逾期事项、新咨询；核实真实项目ID/机会ID。公司、联系人和采购机会分开，不根据昵称合并。
-3. 本人发起单次研究时须明确本次地区和场景；养殖、物业、停车场照明均为测试场景，不是正式默认范围。目标默认10条、最多30条。数量不足如实交付，不凑数据；不自动创建周期任务。
+3. 本人发起单次研究时须明确本次地区和场景；口径见下节。目标默认10条、最多30条。数量不足如实交付，不凑数据；不自动创建周期任务。
 4. 来源优先本次场景相关机构的官方项目资料和采购公告。公开招标采购公告仅收执行当日及此前 6 个北京时间日内发布的项目，以原文发布日期为准；超期、日期不明或仅见转载日期则跳过并在回执说明。普通官网资料不套用该时限。当前由任务指令和人工核验执行，服务端无硬过滤。区分项目地址、企业注册地址和代理地址；区分发布日期与发现日期。行业匹配不等于采购需求。
 5. 经受限工具提交候选或建议，检查ok及真实返回ID；人工审核后由本人联系。拒绝联系先停止触达建议，按工具流程提出停联。
 6. 完成后输出本次结果、真实回执、失败与未知、待用户处理事项；不把草稿写成已发送。
 
+## 场景与字段口径
+
+正式地区为中国，具体省市由本人逐次指定。正式场景按采购组织方式分 5 类：
+
+| 一级分类（scene） | 典型业态 |
+|---|---|
+| 公共建筑 | 学校、医院 |
+| 商业地产 | 酒店、商业综合体 |
+| 居住社区 | 中大型物业小区 |
+| 工业与连锁 | 工厂、连锁商超/药店 |
+| 市政与公共空间 | 市政路灯、地下停车场 |
+
+`scene` 是自由文本，只写上表一级分类；学校、医院、酒店、工厂、商超、药店、市政路灯、地下停车场等细分业态写入检索说明、候选项目名和匹配理由，不自造第六类。
+
+`tags` 只写采购触发类型：新建扩建、存量改造、连锁展店、政策驱动、更换周期；标签词表由本人在工作台维护，Agent 只用 `list_tags` 返回的真实 `tag_id`，不改表结构。
+
+地区+场景仍须本人逐次明确，历史任务、测试样例和看板示例都不能当默认值。六日窗口只对公开招标公告类生效；官网介绍、新闻、企业资料等非公告来源不套用，但仍须核实来源和本次范围。
+
 ## 输出模板（按需创建，不预填假数据）
 
 任务名格式：📋 获客研究 OPS-YYYYMMDD-01；修订r01递增。业务记录主状态仍在工作台，交付文件是带时间的导出/待审草稿。
@@ -24,6 +42,27 @@
 
 通用交付页结构：任务/范围 → 已保存事实与回执 → 待审建议 → 未知/失败 → 用户下一步。只有批准记录能标“已批准”；知识库现行问答逐条看 review、scope、CONF 和版本，不能沿用旧 r19 的“全稿待审”结论。
 
+## 飞书表格口径（方案 A：单向只读快照）
+
+飞书表格只接收工作台导出的脱敏只读快照，用于有效客户数据的收集、整理与查阅。它不承载业务写入，也不作为审核、发送或报价依据。
+
+| 项目 | 规则 |
+|---|---|
+| 数据方向 | 工作台 → 飞书，单向导出；飞书不得回写工作台。 |
+| 快照内容 | 按工作台现有脱敏结果导出；联系人默认脱敏，不含密钥、凭证、Cookie、原始私信全文。 |
+| 飞书内操作 | 只做排序、筛选、查阅和阅读标记；不得修改公司、项目、联系人、阶段、需求、报价等业务字段。 |
+| 状态源 | 始终为工作台数据库 `/Users/dkai2024163.com/ai/data/jxd-leads/current/`；飞书快照带导出时间，过期以工作台为准。 |
+| 第二客户库判断 | 只有单向导出时，飞书不构成“第二客户库”。出现回写、人工改业务字段或双向同步，即按第二客户库处理：立即停止同步，回到工作台审核修正后重新导出。 |
+
+需要更正数据时，在工作台走人工审核或编辑，再重新导出；不在飞书内补字段、改状态或拼客户档案。
+
+## 旧库处置与回滚基线
+
+- 旧 0.3.0 库及其 `backups` 副本归档只读保留三个月，至少至 2027-02-25；路径 `/Users/dkai2024163.com/ai/data/jxd-leads/archive-0.3.0`，目录和文件已去除写权限。
+- 到期处置：整体移入废纸篓，不执行 `rm`，不逐文件删除；移动前复核归档 bundle、哈希清单和回执仍在，移动后记录日期与去向。是否延长保留期由本人决定。
+- 回滚基线：2026-11-25 13:08:49 的 `pre-cutover-final.db`，SHA-256 `1309e1c2fb1eab358296483aae9f048ba339dc246da06d87ded774cf6435e9b8`；路径 `/Users/dkai2024163.com/ai/archive/jingxiaodian-leads-0.3.0-20261125/pre-cutover-final.db`。
+- 回滚快照只读校验，不用它覆盖当前库；恢复必须先到隔离目录，核对完整性和迁移头后再决定是否切换。
+
 ## 知识复用
 
 JXD-KB-001 是现行业务知识主写入口，旧 r19 只作历史证据。直采、EMC 的质保、合作年限、分成与结算分别核对现行 POL 条目及 CONF 修订，不从本段复制数值直接答客。
```

### 3.3 v05 `docs/workbuddy-v1.2.md`

```diff
diff --git a/docs/workbuddy-v1.2.md b/docs/workbuddy-v1.2.md
index 437d385..8319b34 100644
--- a/docs/workbuddy-v1.2.md
+++ b/docs/workbuddy-v1.2.md
@@ -1,6 +1,6 @@
-# 京小电业务助手提示词 v1.2（工作台 0.5.0 候选）
+# 京小电业务助手提示词 v1.2（工作台 0.5.0）
 
-你是京小电的获客与跟进助手。正式工作目录固定为 `/Users/dkai2024163.com/ai/product/jingxiaodian-leads`。只按本人为本次任务明确填写的地区和场景研究候选，并整理客户咨询与下一步；没有指定范围就先请本人明确。养殖、物业、停车场照明均可能出现在隔离测试中，不因此成为正式业务范围。本人负责核实事实、正式报价和实际联系。
+你是京小电的获客与跟进助手。正式工作目录固定为 `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05`；业务数据目录为 `/Users/dkai2024163.com/ai/data/jxd-leads/current/`。只按本人为本次任务明确填写的地区和场景研究候选，并整理客户咨询与下一步；没有指定范围就先请本人明确。正式地区为中国，具体省市由本人逐次指定；正式场景按采购组织方式分 5 类：公共建筑（学校、医院）、商业地产（酒店、商业综合体）、居住社区（中大型物业小区）、工业与连锁（工厂、连锁商超/药店）、市政与公共空间（市政路灯、地下停车场）。未列入五类的场景（如养殖）仅用于隔离测试，不因此成为正式业务范围。本人负责核实事实、正式报价和实际联系。
 
 ## 每次开始
 
@@ -16,11 +16,13 @@
 只有本人明确要求本次研究，并给出地区与场景后，才调用 `create_research_task`；目标默认10条、最多30条，不建立周期任务。随后 `get_research_task`，按照任务范围执行。不得把历史测试任务的范围当作本次默认值。
 创建调用显式传入 `request_id/region/scene/target`；地区或场景缺失返回 `VALIDATION_ERROR` 时停止并取得本人范围，不自动补旧默认。已保存请求重试复用原编号和内容；网页已有任务只读取并使用实际 `task_id`，不重复创建。
 
-网页同时使用 `--data-dir` 和独立的 `--approved-data-dir`，原生 MCP 与备用脚本分别使用 `JXD_DATA_DIR` 和独立的 `JXD_APPROVED_DATA_DIR`。实际目录必须等于维护者批准目录，并先经显式 `migrate` 初始化到候选迁移头；任一缺失、空白、相对路径、目录不一致或数据库未初始化时停止。该配置不属于工具 JSON 参数，不读取数据库来绕过受限工具。新看板（设计 v0.4.0）已在 0.5.0 候选中聚合，原型数据不能用作获客事实或本次任务范围。
+场景写法：`scene` 只填 5 个一级分类之一；学校、医院、酒店、工厂、商超、药店、市政路灯、地下停车场等细分业态写进检索说明、候选项目名和匹配理由，不自造第六类。`tags` 只填采购触发类型（新建扩建/存量改造/连锁展店/政策驱动/更换周期）；先用 `list_tags` 查真实 `tag_id`，词表由本人维护，不擅自新建。
+
+网页同时使用 `--data-dir` 和独立的 `--approved-data-dir`，原生 MCP 与备用脚本分别使用 `JXD_DATA_DIR` 和独立的 `JXD_APPROVED_DATA_DIR`。实际目录必须等于维护者批准目录，并先经显式 `migrate` 初始化到正式迁移头；任一缺失、空白、相对路径、目录不一致或数据库未初始化时停止。该配置不属于工具 JSON 参数，不读取数据库来绕过受限工具。新看板（设计 v0.4.0）已在 0.5.0 中聚合，原型数据不能用作获客事实或本次任务范围。
 
 优先本次场景相关机构的官网、项目原始资料和公开采购公告。每条候选按十项核对：公司全名、具体项目、地区、地址证据、来源 URL、公开单位电话、发现日期、原文摘要、匹配理由、未知项。电话与未知项可留空；电话仅限公开来源可核对的机构号码，不能猜测或把个人号码当单位电话。能确认时补 `publisher/published_at/location_kind/project_state`；不知道就留未知或空值，发布日期不能用发现日代替。能确认时填 `source_channel`，值只能取自 `get_capabilities.source_channels`；招标公告写明截止日时填 `bid_deadline`，且不得早于 `published_at`。
 
-公开招标发布的采购项目只收**执行当日及此前 6 个北京时间日**的公告，首尾日期均计入。以公告原文发布日期填写 `published_at`；发现日期不能代替。日期不明、超出窗口或只找到转载日期的公告不提交为新候选，在 `submit_candidates` 的 `note` 中说明跳过数量和来源。非招标来源不套用这条七日限制，仍须核实来源及本次任务范围。
+公开招标公告类项目只收**执行当日及此前 6 个北京时间日**的公告，首尾日期均计入。以公告原文发布日期填写 `published_at`；发现日期不能代替。日期不明、超出窗口或只找到转载日期的公告不提交为新候选，在 `submit_candidates` 的 `note` 中说明跳过数量和来源。非公告来源不套用这条六日窗口，仍须核实来源及本次任务范围。
 
 候选资料不足或时机未到时，由本人设为 `watch` 并指定复核日期；助手不能代做人工复核。每项新增来源应单独保留 `source_url` 与 `claim`，冲突不得自动合并或覆盖。
 
@@ -45,7 +47,7 @@
 
 ## 判断与标签
 
-先调用 `list_tags`；只使用词表中真实 tag_id。新增词表由本人在工作台操作。
+先调用 `list_tags`；只使用词表中真实 tag_id。新增词表由本人在工作台操作。采购触发类型只放在 `tags`：新建扩建、存量改造、连锁展店、政策驱动、更换周期；`propose_qualification` 和 `propose_opportunity_update` 的 `tag_ids` 只能使用 `list_tags` 返回的真实 ID，Agent 不新造标签。
 
 `propose_qualification` 必须指定且只指定一个 candidate_id 或 opportunity_id，并提供 evidence。字段和取值：
 
@@ -68,6 +70,8 @@
 
 需要整理咨询字段时可调用 `propose_inquiry_fields(inquiry_id, fields, evidence, request_id)`。`fields` 只包含原话有依据的 `company/project_name/region/scene/lamps/demand/purchase_time/annual_power_cost`（八项；电费区间只能是 `≥30万 / 5–30万 / <5万 / 未知`），不知道的项省略，不填“未知”凑数；`evidence` 说明原文依据。建议只进入待审队列，本人逐项核对后才更新咨询。不能通过该工具改处理状态、采购意向、采购机会、报价或自动建项目。同一 `request_id` 重试必须保持字段与依据完全一致。
 
+`scene` 只填一级分类；细分业态（学校、医院、酒店等）写进 `project_name` 或 `demand`，不自造第六类。
+
 回复先回应问题，再逐步确认地区、具体场景、产品或设备规格/数量、主要问题和采购时间；每次只问1—2个必要问题，避免一次发问卷。需要照片或数据时说明用途。`propose_inquiry_reply` 保存待审核草稿；人工修改并确认后本人复制发送。不要声称已私信、已互关、已加企微或已触达。
```

### 3.4 v05 `README.md`（新增）

新增文件，无删除行；完整内容见 `README.md`，本节只作摘要，文件共 54 行。核心变化：删除旧单一地区、单一业态口径；写入五类场景、`scene`/`tags`、飞书只读快照和旧库处置入口。

### 3.5 v05 `docs/INTERNAL-scene-taxonomy.md`（新增）

新增文件，无删除行；完整内容见 `docs/INTERNAL-scene-taxonomy.md`，第 4.1–4.3 节为口径原文摘录，文件共 78 行。它是本口径的内部主文档，包含五类场景、落库方式、触发类型、旧口径处置和变更控制。

## 4. 更新后的口径原文

### 4.1 正式场景口径

正式地区为中国，具体省市由本人逐次指定。正式场景按采购组织方式分 5 类：

| 序号 | 一级分类（scene） | 典型业态 | 典型采购方 |
|---|---|---|---|
| ① | 公共建筑 | 学校、医院 | 事业单位、公共机构 |
| ② | 商业地产 | 酒店、商业综合体 | 业主方、运营方、资产管理方 |
| ③ | 居住社区 | 中大型物业小区 | 物业公司、业委会、社区管理方 |
| ④ | 工业与连锁 | 工厂、连锁商超/药店 | 工厂业主、连锁总部、区域运营方 |
| ⑤ | 市政与公共空间 | 市政路灯、地下停车场 | 市政单位、城投、公共设施管理方 |

分类依据是采购组织方式，不是行业名称。一个任务只选一个一级分类作为主场景；确需跨类时拆成多个任务，或在任务说明中写明主/次，`scene` 仍只写主类。

细分业态不进 `scene`：学校、医院、酒店、工厂、商超、药店、市政路灯、地下停车场等写入检索说明、候选项目名、匹配理由或咨询的 `project_name/demand`。不自造第六类，也不把行业匹配当成采购需求。

`scene` 是自由文本，只写一级分类；`tags` 只写采购触发类型：新建扩建、存量改造、连锁展店、政策驱动、更换周期。不改表结构：不新增场景枚举、不新增 tags 表、不改迁移。标签词表由本人在工作台维护，Agent 只用 `list_tags` 返回的真实 `tag_id`，不擅自新增。

地区+场景仍须本人逐次明确，历史任务、测试样例和看板示例都不能当默认值。六日窗口只对公开招标公告类生效；非公告来源不套用，但仍须核实来源和本次范围。

### 4.2 飞书口径（方案 A）

飞书表格只接收工作台导出的脱敏只读快照，用于有效客户数据的收集、整理与查阅。它不承载业务写入，也不作为审核、发送或报价依据。

| 项目 | 规则 |
|---|---|
| 数据方向 | 工作台 → 飞书，单向导出；飞书不得回写工作台。 |
| 快照内容 | 按工作台现有脱敏结果导出；联系人默认脱敏，不含密钥、凭证、Cookie、原始私信全文。 |
| 飞书内操作 | 只做排序、筛选、查阅和阅读标记；不得修改公司、项目、联系人、阶段、需求、报价等业务字段。 |
| 状态源 | 始终为工作台数据库 `/Users/dkai2024163.com/ai/data/jxd-leads/current/`；飞书快照带导出时间，过期以工作台为准。 |
| 第二客户库判断 | 只有单向导出时，飞书不构成“第二客户库”。出现回写、人工改业务字段或双向同步，即按第二客户库处理：立即停止同步，回到工作台审核修正后重新导出。 |

需要更正数据时，在工作台走人工审核或编辑，再重新导出；不在飞书内补字段、改状态或拼客户档案。

### 4.3 旧库处置与回滚基线

- 旧 0.3.0 库及其 `backups` 副本归档只读保留三个月，至少至 2027-02-25；路径 `/Users/dkai2024163.com/ai/data/jxd-leads/archive-0.3.0`，目录和文件已去除写权限。
- 到期处置：整体移入废纸篓，不执行 `rm`，不逐文件删除；移动前复核归档 bundle、哈希清单和回执仍在，移动后记录日期与去向。是否延长保留期由本人决定。
- 回滚基线：2026-11-25 13:08:49 的 `pre-cutover-final.db`，SHA-256 `1309e1c2fb1eab358296483aae9f048ba339dc246da06d87ded774cf6435e9b8`；路径 `/Users/dkai2024163.com/ai/archive/jingxiaodian-leads-0.3.0-20261125/pre-cutover-final.db`。
- 回滚快照只读校验，不用它覆盖当前库；恢复必须先到隔离目录，核对完整性和迁移头后再决定是否切换。

### 4.4 v05 README 现行口径

`README.md` 已写入以下现行内容：正式工程 `jingxiaodian-leads-v05`、业务数据 `jxd-leads/current/`、五类场景、`scene`/`tags` 写法、飞书只读快照、旧库三个月与废纸篓处置，并链接内部口径和主控 operations。旧 0.3.0 的单一地区、单一业态描述未复制到新 README。

### 4.5 WorkBuddy 提示词关键段

正式工作目录固定为 `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05`；业务数据目录为 `/Users/dkai2024163.com/ai/data/jxd-leads/current/`。正式地区为中国，具体省市由本人逐次指定；正式场景按采购组织方式分 5 类。`scene` 只填一级分类；细分业态写检索说明、候选项目名和匹配理由。`tags` 只填采购触发类型，先用 `list_tags` 查真实 `tag_id`。公开招标公告类只收执行当日及此前 6 个北京时间日的公告；非公告来源不套用这条六日窗口。

### 4.6 协作操作手册 r06 首段

```diff
--- docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md（r06 变更前）
+++ docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md
@@ -5,1 +5,1 @@
-本手册按当前本地文档、页面模板和受限工具定义编写。0.5.0 候选不预设正式业务地区或场景；养殖、物业、停车场照明仅为隔离测试中出现的场景。你负责指定每次范围、核实、批准和联系客户；AI 负责研究、整理与提交建议。
+本手册按当前本地文档、页面模板和受限工具定义编写。正式地区为中国，具体省市逐次指定；正式场景按采购组织方式分五类（公共建筑、商业地产、居住社区、工业与连锁、市政与公共空间），口径见 `docs/INTERNAL-scene-taxonomy.md`。养殖仅为隔离测试场景，不属正式范围。你负责指定每次范围、核实、批准和联系客户；AI 负责研究、整理与提交建议。
```

补充说明：该文件其余章节的旧工程路径 `/Users/dkai2024163.com/ai/product/jingxiaodian-leads` 本轮未改，理由见第 6 节；只处理与新口径直接冲突的首段。

## 5. 验证

### 5.1 旧表述清除

```sh
rg -n "养殖、物业|物业、停车场照明|测试场景，不作正式默认范围|不是正式默认范围|成都及周边物业直采" \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/AGENTS.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/operations.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/workbuddy-v1.2.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/README.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/INTERNAL-scene-taxonomy.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md
```

结果：无输出，`exit=1`（未命中）。旧表述已在六个现行文件中清除；本回执第 3 节保留删除行原文，属留证，不参与该 grep。

### 5.2 新口径存在

```sh
rg -l "正式地区为中国|公共建筑|商业地产|居住社区|工业与连锁|市政与公共空间" \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/AGENTS.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/operations.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/workbuddy-v1.2.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/README.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/INTERNAL-scene-taxonomy.md \
  /Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md
```

结果：命中 6 个文件：

```text
/Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/AGENTS.md
/Users/dkai2024163.com/ai/product/jingxiaodian-leads-hub/operations.md
/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/workbuddy-v1.2.md
/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/INTERNAL-scene-taxonomy.md
/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/README.md
/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md
```

### 5.3 回滚快照哈希

```sh
shasum -a 256 /Users/dkai2024163.com/ai/archive/jingxiaodian-leads-0.3.0-20261125/pre-cutover-final.db
```

结果：

```text
1309e1c2fb1eab358296483aae9f048ba339dc246da06d87ded774cf6435e9b8  /Users/dkai2024163.com/ai/archive/jingxiaodian-leads-0.3.0-20261125/pre-cutover-final.db
```

与本人指定值一致；文件大小 577536 字节，mtime `2026-11-25 13:08`。

### 5.4 工作树状态

```sh
git status --short
```

结果：

```text
 M docs/workbuddy-v1.2.md
 M docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md
?? README.md
?? docs/INTERNAL-scene-taxonomy.md
?? docs/verify/202611/20261125-scope-taxonomy-r01.md
?? native/
?? scripts/build-notifications.py
```

说明：`native/` 和 `scripts/build-notifications.py` 是阶段 A 已存在的未跟踪项，本轮未触碰。`docs/verify/202611/20261125-scope-taxonomy-r01.md` 是本回执。本轮新增/修改仅文档。

```sh
git diff --numstat -- docs/workbuddy-v1.2.md
```

结果：

```text
9	5	docs/workbuddy-v1.2.md
1	1	docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md
```

新增文件行数：`README.md` 54 行；`docs/INTERNAL-scene-taxonomy.md` 78 行。

### 5.5 新增文件 diff 复现

```sh
git diff --no-index -- /dev/null README.md
git diff --no-index -- /dev/null docs/INTERNAL-scene-taxonomy.md
```

两条命令分别输出新增文件的完整 unified diff；`--no-index` 在存在差异时退出码为 1，属正常结果。

## 6. 未改与残留

| 项 | 状态 | 说明 |
|---|---|---|
| Python / 配置 / 数据库 | 未改 | `git status` 无 `src/`、`migrations/`、`pyproject.toml`、`runtime/`、`data/` 变更 |
| 8765 服务 | 未动 | 未启动、停止、重启或请求 8765 |
| `docs/workbuddy.md` | 未改 | 仍有旧工程路径 `/Users/dkai2024163.com/ai/product/jingxiaodian-leads` 和“正式 0.3.0”表述；不在本任务范围，建议下一步统一 |
| `docs/京小电获客工作台-Codex与WorkBuddy协作操作手册-r03.md` | 部分改 | 首段场景口径已改；第 11 行等多处仍写旧工程路径 `/Users/dkai2024163.com/ai/product/jingxiaodian-leads`（该目录已不存在），建议与 `workbuddy.md` 一起做路径批量更新 |
| `docs/INTERNAL-directory-map.md` | 未改 | 仍写旧工程“待阶段 B 决定退役”；阶段 B 已完成，建议后续更新 |
| 0.3.0 归档/废纸篓 README | 未改 | 历史证据保留原样；旧表述只在归档中出现，现行 v05 README 已清除 |
| 五类采购触发标签 | 未写入数据库 | 本轮只定口径；工作台标签词表仍需本人在 UI 建立，Agent 不得擅自新增 |

## 7. 约束确认

- 本轮只改文档；未改 Python 代码、配置、数据库结构或正式数据。
- 未启动、停止、重启或请求 8765。
- 未提交、未推送、未发布、未发送任何外部消息。
- 旧库归档和回滚快照只读校验，未覆盖、未删除。
