from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

from health_agent_bridge.apple_health_importer import AppleHealthXmlImporter
from health_agent_bridge.config import settings
from health_agent_bridge.database import Database
from health_agent_bridge.export_archive import newest_export_in


def refresh_agent_summary(api_base: str, api_key: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/health/summary/today",
        headers={"X-API-Key": api_key},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sync the newest Apple Health zip/xml from storage using incremental import."
        ),
    )
    parser.add_argument(
        "export_path",
        type=Path,
        nargs="?",
        help="Path to export.zip or export.xml. Defaults to newest zip in storage/.",
    )
    parser.add_argument("--storage-dir", type=Path, default=Path("storage"))
    parser.add_argument("--user-name", default=settings.user_name)
    parser.add_argument("--db-path", type=Path, default=settings.db_path)
    parser.add_argument("--db-backend", default=settings.db_backend)
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--state-path", type=Path, default=Path("storage/import_state.json"))
    parser.add_argument("--overlap-days", type=int, default=14)
    parser.add_argument("--full", action="store_true", help="Re-import all history.")
    parser.add_argument("--force", action="store_true", help="Import even if zip hash unchanged.")
    parser.add_argument(
        "--refresh-summary",
        action="store_true",
        help="Call GET /health/summary/today after import.",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("HEALTH_BRIDGE_API_BASE", "http://127.0.0.1:8012"),
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("HEALTH_BRIDGE_API_KEY", settings.api_key),
    )
    args = parser.parse_args()

    export_path = args.export_path
    if export_path is None:
        export_path = newest_export_in(args.storage_dir)
    if export_path is None or not export_path.exists():
        raise SystemExit(f"No Apple Health export found in {args.storage_dir}")

    database = Database(
        db_path=args.db_path,
        backend=args.db_backend,
        database_url=args.database_url,
    )
    importer = AppleHealthXmlImporter(database)
    result = importer.import_export(
        export_path=export_path,
        user_name=args.user_name,
        state_path=args.state_path,
        incremental=not args.full,
        overlap_days=args.overlap_days,
        force=args.force,
    )

    payload: dict[str, object] = {
        "export_path": str(export_path),
        "skipped": result.skipped,
        "skip_reason": result.skip_reason,
        "import_mode": result.import_mode,
        "imported_days": result.imported_days,
        "start_date": result.start_date.isoformat() if result.start_date else None,
        "end_date": result.end_date.isoformat() if result.end_date else None,
        "state_path": str(args.state_path),
    }

    if args.refresh_summary and not result.skipped:
        payload["summary"] = refresh_agent_summary(args.api_base, args.api_key)

    print(json.dumps(payload, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
