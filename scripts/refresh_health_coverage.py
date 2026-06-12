from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from health_agent_bridge.config import settings
from health_agent_bridge.database import Database
from health_agent_bridge.health_coverage import write_health_coverage
from health_agent_bridge.repository import HealthRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh health_coverage.json for care agent.")
    parser.add_argument("--storage-dir", type=Path, default=Path("storage"))
    parser.add_argument("--user-name", default=settings.user_name)
    parser.add_argument("--db-path", type=Path, default=settings.db_path)
    parser.add_argument("--db-backend", default=settings.db_backend)
    parser.add_argument("--database-url", default=settings.database_url)
    args = parser.parse_args()

    database = Database(
        db_path=args.db_path,
        backend=args.db_backend,
        database_url=args.database_url,
    )
    repository = HealthRepository(database)
    care_context_dir = Path(
        os.environ.get(
            "HEALTH_EXPORT_COVERAGE_CONTEXT_DIR",
            "/home/mauro/Dev/openclaw-mauro/data/workspace/care/context",
        )
    )
    path = write_health_coverage(
        repository=repository,
        user_name=args.user_name,
        storage_dir=args.storage_dir,
        care_context_dir=care_context_dir,
        timezone=settings.timezone,
        clear_pending=False,
    )
    print(json.dumps({"health_coverage_path": str(path)}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
