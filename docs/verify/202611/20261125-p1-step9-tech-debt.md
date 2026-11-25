# 第 9 步｜技术债处理回执

日期：2026-11-25
状态：代码与本地验证完成；未提交，未动 8765

## 1. 通知助手路径

- `src/jxd_leads/desktop.py` 支持 `JXD_NOTIFICATION_HELPER` 环境变量；未设置时仍回退到工程根目录下的 `runtime/JXDNotifications.app/Contents/MacOS/JXDNotifications`。
- `启动工作台.command` 显式导出该环境变量，指向 v05 的 `runtime` 真实可执行文件。
- `.venv/lib/python3.12/runtime/JXDNotifications.app` 原软链已移动到 `/tmp/jxd-p1-symlink-backup/JXDNotifications.app`，未执行 `rm`。`.venv/lib/python3.12/runtime/` 现为空目录。
- 未设置环境变量时，默认路径解析为：
  `/Users/dkai2024163.com/ai/product/jingxiaodian-leads-v05/runtime/JXDNotifications.app/Contents/MacOS/JXDNotifications`
  该文件存在。
- `status` 实测返回 `authorization=not_determined`、`enabled=False`；未申请授权、未发送系统通知、未改钥匙串。

证据：`docs/verify/202611/20261125-p1-step9-notifications.txt`

## 2. 启动器端口参数化

- `启动工作台.command` 使用 `PORT="${JXD_PORT:-8765}"`，并传给 `jxd-leads serve --port "$PORT"`。
- 默认值仍为 8765；本次未启动或重启 8765。
- 该文件在 `.git/info/exclude` 中，不进入 git；当前 SHA-256：
  `b3a544e47e8eb03b60f1fdb054ad6f3fdacddc4fe24eab3485a4becdf5d9423e`

## 3. native/ 与构建脚本归属

- `native/notifications/main.swift`：纳入 git，作为通知助手源码。
- `scripts/build-notifications.py`：纳入 git，作为构建脚本。
- `runtime/`：继续由 `.gitignore` 第 11 行排除，构建产物不入库。
- 已在 `docs/INTERNAL-directory-map.md` 增加归属表。
- `docs/INTERNAL-directory-map.md` 当前 SHA-256：
  `7d299551f7bf057f02a47f6d1e8e7fe8f02c3ed6dd308f0a5f1ca67b64566c9a`
- 两项从 stash `native-notify-and-build-script-for-step9`（对象 `40cd4194301162cd49fb1bba1f5f0e7d2b5d1459`）取回，stash 仍保留。

## 4. 版本号来源

- `src/jxd_leads/__init__.py` 使用 `importlib.metadata.version("jxd-leads")` 生成 `__version__`。
- `web.py` 的 FastAPI 与 `/health`、`workflows.capabilities` 均引用同一个 `__version__`。
- 未新增版本号来源；实测 `__version__=0.5.0`，与安装元数据一致。
- 定向测试：`tests/test_mcp_transport.py tests/test_safety.py`，17 passed。

## 5. 未完成项

- 代码尚未提交，严格门禁因此仍报“工作树未提交”。
- 第 8 步未执行；8765 未重启，未生成新快照。
