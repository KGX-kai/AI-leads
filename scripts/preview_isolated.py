"""Run the 0.5.0 candidate with a temporary database and ephemeral key."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(ROOT / "src"))
    import jxd_leads
    from jxd_leads.db import Database
    from jxd_leads.security import Vault
    from jxd_leads.service import Service
    from jxd_leads.web import create_app

    if not Path(jxd_leads.__file__).resolve().is_relative_to(ROOT):
        raise RuntimeError("隔离预览必须加载本候选源码")
    with TemporaryDirectory(prefix="jxd-leads-0.4-preview-") as temporary:
        database = Database(Path(temporary) / "preview.db")
        database.migrate()
        app = create_app(Service(database, Vault.ephemeral()), testing=True)
        print("隔离预览：http://127.0.0.1:8877/；数据随进程退出删除", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=8877, access_log=False)


if __name__ == "__main__":
    main()
