"""Narrow native notification adapter. No customer content or arbitrary URL crosses this boundary."""

import json
import os
import subprocess
from pathlib import Path

from filelock import FileLock
from sqlalchemy import select

from .db import ROOT
from .models import Notification, Setting, now


class DesktopNotifications:
    def __init__(self, db, helper=None):
        self.db = db
        configured = helper or os.environ.get("JXD_NOTIFICATION_HELPER", "")
        self.helper = Path(configured) if configured else ROOT / (
            "runtime/JXDNotifications.app/Contents/MacOS/JXDNotifications"
        )

    def call(self, command, *args):
        if command not in {"status", "request", "notify", "delivered"}:
            return {"error": "invalid_command"}
        if not self.helper.is_file():
            return {"error": "helper_unavailable", "authorization": "unavailable"}
        try:
            with FileLock(self.db.path.parent / ".notification-helper.lock", timeout=2):
                response = subprocess.run(
                    [str(self.helper), command, *map(str, args)],
                    capture_output=True,
                    timeout=45 if command == "request" else 10,
                    check=False,
                )
            if response.returncode or len(response.stdout) > 65536:
                return {"error": "helper_failed"}
            return json.loads(response.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired, TimeoutError):
            return {"error": "helper_unavailable"}

    def configure(self, enabled):
        state = self.call("request") if enabled else self.call("status")
        active = enabled and state.get("authorization") in {"authorized", "provisional"}
        with self.db.session() as s:
            setting = s.get(Setting, "desktop_enabled")
            if setting:
                setting.value = "true" if active else "false"
            else:
                s.add(Setting(key="desktop_enabled", value="true" if active else "false"))
        return state

    def status(self):
        state = self.call("status")
        with self.db.read_session() as s:
            setting = s.get(Setting, "desktop_enabled")
            state["enabled"] = bool(setting and setting.value == "true")
        return state

    def dispatch(self):
        with FileLock(self.db.path.parent / ".notification-dispatch.lock", timeout=2):
            self._dispatch()

    def _dispatch(self):
        with self.db.session() as s:
            setting = s.get(Setting, "desktop_enabled")
            if not setting or setting.value != "true":
                return
            # A crash after submission has uncertain delivery. Never blindly resend.
            for stale in s.scalars(select(Notification).where(Notification.desktop_status == "dispatching")):
                stale.desktop_status = "uncertain"
            pending = s.scalars(
                select(Notification)
                .where(Notification.desktop_status == "pending", Notification.read_at.is_(None))
                .order_by(Notification.created_at)
                .limit(100)
            ).all()
            if not pending:
                return
            identifiers = [n.id for n in pending]
            count = sum(n.count for n in pending)
            for n in pending:
                n.desktop_status = "dispatching"
                n.desktop_attempted_at = now()
        state = self.call("notify", identifiers[0], count)
        status = (
            "accepted"
            if state.get("status") == "accepted"
            else ("not_authorized" if state.get("error") == "notification_not_authorized" else "uncertain")
        )
        with self.db.session() as s:
            for identifier in identifiers:
                n = s.get(Notification, identifier)
                n.desktop_status = status
                n.desktop_error = state.get("error", "")
