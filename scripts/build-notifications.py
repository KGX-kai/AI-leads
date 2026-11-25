#!/usr/bin/env python3
"""Build once when source changes; never read signing credentials."""

import hashlib
import plistlib
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "native/notifications/main.swift"
app = root / "runtime/JXDNotifications.app"
fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
marker = root / "runtime/notifications-source.sha256"
if marker.exists() and marker.read_text() == fingerprint and (app / "Contents/MacOS/JXDNotifications").exists():
    print("通知助手已是当前版本，保留签名身份")
    raise SystemExit(0)
(app / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
info = {
    "CFBundleIdentifier": "com.jingxiaodian.leads.notifications",
    "CFBundleExecutable": "JXDNotifications",
    "CFBundlePackageType": "APPL",
    "CFBundleName": "京小电获客提醒",
    "CFBundleDisplayName": "京小电获客提醒",
    "CFBundleVersion": "1",
    "CFBundleShortVersionString": "1.0",
    "LSUIElement": True,
    "NSPrincipalClass": "NSApplication",
    "LSMinimumSystemVersion": "12.0",
}
(app / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
subprocess.run(
    [
        "/usr/bin/swiftc",
        "-swift-version",
        "5",
        "-framework",
        "AppKit",
        "-framework",
        "UserNotifications",
        str(source),
        "-o",
        str(app / "Contents/MacOS/JXDNotifications"),
    ],
    check=True,
)
subprocess.run(
    ["/usr/bin/codesign", "--force", "--sign", "-", "--identifier", "com.jingxiaodian.leads.notifications", str(app)],
    check=True,
)
subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(app)], check=True)
marker.write_text(fingerprint)
print("通知助手编译和本机签名检查通过；尚未申请系统授权或发送通知")
