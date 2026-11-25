"""Subprocess fixture with synthetic data and an in-memory test encryption key."""

import sys
from pathlib import Path

from jxd_leads.db import Database
from jxd_leads.mcp_server import create_mcp
from jxd_leads.models import Company, Opportunity, Project
from jxd_leads.security import Vault
from jxd_leads.service import Service

if __name__ == "__main__":
    db = Database(Path(sys.argv[1]) / "transport.db")
    db.migrate()
    with db.session() as session:
        session.add(Company(id="test-company", name="合成物业", region="成都", identity_key="test-company-key"))
        session.flush()
        session.add(
            Project(
                id="test-project",
                company_id="test-company",
                name="合成车库",
                region="成都",
                address="测试",
                identity_key="test-project-key",
            )
        )
        session.flush()
        session.add(Opportunity(id="test-opportunity", project_id="test-project", name="合成采购"))
    service = Service(db, Vault.ephemeral())
    service.receive_inquiry(
        {
            "platform": "手工",
            "account_id": "synthetic-account",
            "message_id": "synthetic-message",
            "body": "成都停车场需要灯具替换方案",
            "occurred_at": "2026-11-15T10:00:00+08:00",
        },
        "synthetic-inquiry",
    )
    create_mcp(service).run(transport="stdio")
