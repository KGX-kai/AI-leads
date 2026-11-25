import hashlib
import hmac
import json
import re
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock

from .errors import BusinessError


class Vault:
    def __init__(self, key: bytes):
        self._key = key
        self._fernet = Fernet(key)

    @classmethod
    def ephemeral(cls):
        """Only for isolated tests. Never selected by production configuration."""
        return cls(Fernet.generate_key())

    @classmethod
    def macos(cls, namespace="production", db=None, before_migration=False):
        from keyring.backends.macOS import Keyring
        from keyring.errors import KeyringError

        ring = Keyring()
        service = "com.jingxiaodian.leads.v1"
        lock_dir = Path.home() / "Library" / "Caches" / "jingxiaodian-leads"
        lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with FileLock(lock_dir / "keychain-init.lock", timeout=15):
            try:
                key = ring.get_password(service, namespace)
            except (KeyringError, OSError):
                raise BusinessError(
                    "系统钥匙串暂不可用；数据未打开，请解锁钥匙串后重试", "KEY_UNAVAILABLE", True
                ) from None
            if key is None:
                if db is not None and not cls.new_database(db):
                    raise BusinessError(
                        "原密钥不可用。已停止打开数据；请恢复本应用钥匙串密钥，不要重新生成。", "KEY_UNAVAILABLE"
                    )
                key = Fernet.generate_key().decode()
                try:
                    ring.set_password(service, namespace, key)
                except (KeyringError, OSError):
                    raise BusinessError("无法保存本应用密钥；已停止初始化", "KEY_UNAVAILABLE", True) from None
        vault = cls(key.encode())
        if db is not None:
            if before_migration:
                vault.preflight(db)
            else:
                vault.validate_database(db)
        return vault

    @classmethod
    def macos_existing(cls, namespace="production"):
        """Read an existing key without ever generating a replacement."""
        from keyring.backends.macOS import Keyring
        from keyring.errors import KeyringError

        try:
            key = Keyring().get_password("com.jingxiaodian.leads.v1", namespace)
        except (KeyringError, OSError):
            raise BusinessError(
                "系统钥匙串暂不可用；数据未打开，请解锁钥匙串后重试", "KEY_UNAVAILABLE", True
            ) from None
        if key is None:
            raise BusinessError("原密钥不可用；未激活恢复目标，请恢复本应用钥匙串密钥", "KEY_UNAVAILABLE")
        return cls(key.encode())

    @staticmethod
    def new_database(db):
        from .db import has_business_data

        with db.session() as s:
            return not has_business_data(s.connection())

    def preflight(self, db, *, immutable=False):
        """Validate existing ciphertext before any schema migration, including v1 databases."""
        import sqlite3

        if not db.path.exists():
            return
        fields = {
            "contacts": "encrypted",
            "followups": "summary",
            "inquiries": "encrypted",
            "review_suggestions": "encrypted",
            "suppression_events": "encrypted",
            "entity_changes": "encrypted",
        }
        try:
            uri = f"file:{db.path}?mode=ro" + ("&immutable=1" if immutable else "")
            with sqlite3.connect(uri, uri=True) as connection:
                tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "key_metadata" in tables:
                    for (sentinel,) in connection.execute("SELECT sentinel FROM key_metadata"):
                        if self.decrypt(sentinel) != {"application": "JXD-LEADS-001", "version": 1}:
                            raise InvalidToken()
                for table, column in fields.items():
                    if table in tables:
                        for (ciphertext,) in connection.execute(f'SELECT "{column}" FROM "{table}"'):
                            self.decrypt(ciphertext)
                if "proposals" in tables:
                    for (value,) in connection.execute("SELECT payload FROM proposals"):
                        self.decrypt(json.loads(value)["encrypted"])
        except (InvalidToken, ValueError, KeyError, TypeError):
            raise BusinessError("原密钥与现有数据不匹配，迁移尚未开始，请恢复匹配密钥", "KEY_UNAVAILABLE") from None

    def validate_database(self, db):
        from sqlalchemy import select

        from .models import (
            Contact,
            EntityChange,
            Followup,
            Inquiry,
            KeyMetadata,
            Proposal,
            ReviewSuggestion,
            SuppressionEvent,
        )

        with db.session() as s:
            metadata = s.get(KeyMetadata, 1)
            try:
                if metadata and self.decrypt(metadata.sentinel) != {"application": "JXD-LEADS-001", "version": 1}:
                    raise InvalidToken()
                for model, field in [
                    (Contact, Contact.encrypted),
                    (Followup, Followup.summary),
                    (Inquiry, Inquiry.encrypted),
                    (ReviewSuggestion, ReviewSuggestion.encrypted),
                    (SuppressionEvent, SuppressionEvent.encrypted),
                    (EntityChange, EntityChange.encrypted),
                ]:
                    for value in s.scalars(select(field)):
                        self.decrypt(value)
                for value in s.scalars(select(Proposal.payload)):
                    self.decrypt(value["encrypted"])
                if not metadata:
                    s.add(
                        KeyMetadata(
                            id=1,
                            version=1,
                            key_ref="com.jingxiaodian.leads.v1/production",
                            sentinel=self.encrypt({"application": "JXD-LEADS-001", "version": 1}),
                        )
                    )
            except (InvalidToken, ValueError, KeyError, TypeError):
                raise BusinessError(
                    "密钥与数据不匹配，已停止写入。请恢复原密钥或匹配的备份。", "KEY_UNAVAILABLE"
                ) from None

    def encrypt(self, data):
        return self._fernet.encrypt(json.dumps(data, ensure_ascii=False).encode()).decode()

    def decrypt(self, value):
        return json.loads(self._fernet.decrypt(value.encode()))

    def fingerprint(self, value):
        compact = re.sub(r"[\s()（）-]", "", value)
        phone = re.fullmatch(r"(?:(?:\+?86|0086))?(1[3-9]\d{9})", compact)
        if phone:
            normalized = "phone:86:" + phone.group(1)
        elif "@" in value:
            normalized = "email:" + value.strip().casefold()
        else:
            normalized = "handle:" + value.strip()
        return hmac.new(self._key, normalized.encode(), hashlib.sha256).hexdigest()


def mask(value):
    if not value:
        return "未填写"
    if "@" in value:
        local, domain = value.split("@", 1)
        return local[:1] + "***@" + domain
    return value[:3] + "****" + value[-2:] if len(value) > 6 else value[:1] + "***"


_DATE_PREFIX = re.compile(r"\(?\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?!\d)")
_TIME_PREFIX = re.compile(r"\d{1,2}:\d{2}:$")
_NUMBER_TOKEN = re.compile(r"(?<!\d)(?:\+?86[ \t\-.]?)?\(?\d[\d \t().|｜\-－．（）]{4,}\d\)?(?!\d)")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _redact_numbers(value):
    def replace(match):
        token = match.group(0)
        if _DATE_PREFIX.match(token.lstrip("(")) or _TIME_PREFIX.search(value[: match.start()]):
            return token
        if len(re.sub(r"\D", "", token)) < 7:
            return token
        return "[号码已隐藏]"

    return _NUMBER_TOKEN.sub(replace, value)


def redact(value):
    stripped = value.strip()
    is_url = stripped.lower().startswith(("http://", "https://")) and not re.search(r"\s", stripped)
    held = []

    def hold_uuid(match):
        held.append(match.group(0))
        return f"\x00{len(held) - 1}\x00"

    value = _UUID.sub(hold_uuid, value)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱已隐藏]", value)
    value = re.sub(r"(?<!\d)(?:(?:\+?86|0086)[ -]?)?1[3-9]\d[ -]?\d{4}[ -]?\d{4}(?!\d)", "[手机号已隐藏]", value)
    if not is_url:
        value = _redact_numbers(value)
    for index, identifier in enumerate(held):
        value = value.replace(f"\x00{index}\x00", identifier)
    return value
