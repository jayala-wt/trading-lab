from __future__ import annotations

from pathlib import Path

from core.common.env import load_dotenv
from core.common.paths import repo_root
from core.data.db import Database, apply_migrations, log_dev_event


def main() -> None:
    load_dotenv(repo_root() / ".env")
    db_path = Path(
        __import__("os").getenv("TRADING_LAB_DB_PATH", str(repo_root() / "data" / "market.db"))
    )
    db = Database(db_path)
    apply_migrations(db)
    log_dev_event(db, "INFO", "migration", "Database migrations applied", {"db": str(db_path)})


if __name__ == "__main__":
    main()
