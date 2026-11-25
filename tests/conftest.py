import pytest

from jxd_leads.db import Database
from jxd_leads.security import Vault
from jxd_leads.service import Service


@pytest.fixture
def svc(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    return Service(db, Vault.ephemeral())
