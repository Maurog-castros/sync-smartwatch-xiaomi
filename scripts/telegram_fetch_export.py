from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path

from health_agent_bridge.export_archive import export_file_sha256
from health_agent_bridge.whatsapp_sync_state import WhatsAppSyncState


DEFAULT_HERMES_CACHE = Path(
    "/home/mauro/Dev/hermes-openclaw-benchmark/.hermes/cache/documents"
)
DEFAULT_FILENAME = "exportar.zip"


def _find_latest_export(
    cache_dir: Path,
    filename: str,
    max_age_minutes: int | None,
) -> Path | None:
    if not cache_dir.exists():
        return None

    candidates = [
        path
        for path in cache_dir.glob(f"*{filename}")
        if path.is_file()
    ]
    if not candidates:
        candidates = [
            path
            for path in cache_dir.glob("*.zip")
            if path.is_file() and filename.lower() in path.name.lower()
        ]
    if not candidates:
        return None

    if max_age_minutes is not None:
        cutoff = time.time() - (max_age_minutes * 60)
        candidates = [path for path in candidates if path.stat().st_mtime >= cutoff]

    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def fetch_latest_export(
    *,
    cache_dir: Path,
    storage_dir: Path,
    filename: str,
    max_age_minutes: int | None,
) -> dict[str, object]:
    source = _find_latest_export(cache_dir, filename, max_age_minutes)
    if source is None:
        return {
            "downloaded": False,
            "skip_reason": "no_telegram_export_found",
            "cache_dir": str(cache_dir),
        }

    target = storage_dir / filename
    state_path = storage_dir / "telegram_sync_state.json"
    state = WhatsAppSyncState.load(state_path)
    file_hash = export_file_sha256(source)
    file_size = source.stat().st_size

    if (
        state.last_download_sha256 == file_hash
        and state.last_download_size == file_size
    ):
        return {
            "downloaded": False,
            "skip_reason": "telegram_file_unchanged",
            "source_path": str(source),
            "target_zip": str(target),
            "sha256": file_hash,
        }

    storage_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    state.last_download_path = str(target)
    state.last_download_sha256 = file_hash
    state.last_download_size = file_size
    state.last_message_label = source.name
    state.last_sync_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    state.save(state_path)

    return {
        "downloaded": True,
        "skip_reason": None,
        "source_path": str(source),
        "target_zip": str(target),
        "sha256": file_hash,
        "size_bytes": file_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy latest Apple Health export zip from Hermes Telegram cache.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(os.environ.get("HEALTH_EXPORT_TELEGRAM_CACHE_DIR", DEFAULT_HERMES_CACHE)),
    )
    parser.add_argument("--storage-dir", type=Path, default=Path("storage"))
    parser.add_argument(
        "--filename",
        default=os.environ.get("WHATSAPP_EXPORT_FILENAME", DEFAULT_FILENAME),
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=None,
        help="Only accept exports newer than this many minutes. Default: any age.",
    )
    args = parser.parse_args()

    result = fetch_latest_export(
        cache_dir=args.cache_dir,
        storage_dir=args.storage_dir,
        filename=args.filename,
        max_age_minutes=args.max_age_minutes,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
