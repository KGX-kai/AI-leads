"""Isolated browser acceptance sandbox. Synthetic data only; no production keyring."""

import tempfile
from pathlib import Path

import uvicorn

from jxd_leads.db import ROOT, Database
from jxd_leads.schemas import CandidateInput
from jxd_leads.security import Vault
from jxd_leads.service import Service
from jxd_leads.web import create_app

if __name__ == "__main__":
    folder = Path(tempfile.mkdtemp(prefix="browser-qa-", dir=ROOT / "work"))
    db = Database(folder / "leads.db")
    db.migrate()
    service = Service(db, Vault.ephemeral())
    service.submit_candidates(
        None,
        [
            CandidateInput(
                company="合成回归物业",
                project="筛选后审核验收",
                region="成都",
                source_type="已有关系",
                evidence="合成验收数据，无真实客户",
            )
        ],
        actor="owner",
    )
    app = create_app(service, folder / "backups")
    uvicorn.run(app, host="127.0.0.1", port=8766, access_log=False)
