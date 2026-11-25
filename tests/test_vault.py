from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import sleep

from jxd_leads.security import Vault


def test_concurrent_keychain_initialization(monkeypatch, tmp_path):
    from keyring.backends import macOS

    stored = {}

    class FakeRing:
        def get_password(self, service, account):
            sleep(0.03)
            return stored.get((service, account))

        def set_password(self, service, account, value):
            stored[(service, account)] = value

    monkeypatch.setattr(macOS, "Keyring", FakeRing)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        vaults = list(pool.map(lambda _: Vault.macos("synthetic-test"), range(2)))
    for vault in vaults:
        assert vaults[0].decrypt(vault.encrypt({"text": "synthetic"})) == {"text": "synthetic"}


def test_fresh_migrated_database_can_initialize_without_key(monkeypatch, tmp_path):
    from keyring.backends import macOS

    from jxd_leads.db import Database

    db = Database(tmp_path / "new.db")
    db.migrate()
    stored = {}

    class FakeRing:
        def get_password(self, service, account):
            return stored.get(account)

        def set_password(self, service, account, value):
            stored[account] = value

    monkeypatch.setattr(macOS, "Keyring", FakeRing)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    vault = Vault.macos("new", db=db)
    assert vault.decrypt(vault.encrypt({"test": 1})) == {"test": 1}
    stored.clear()
    import pytest

    from jxd_leads.errors import BusinessError

    with pytest.raises(BusinessError) as error:
        Vault.macos("new", db=db)
    assert error.value.code == "KEY_UNAVAILABLE"
    assert stored == {}
