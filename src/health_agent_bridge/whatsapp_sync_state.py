from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class WhatsAppSyncState:
    last_download_path: str | None = None
    last_download_sha256: str | None = None
    last_download_size: int | None = None
    last_message_label: str | None = None
    last_sync_at: str | None = None

    @classmethod
    def load(cls, path: Path) -> WhatsAppSyncState:
        if not path.exists():
            return cls()
        return cls(**{**asdict(cls()), **json.loads(path.read_text(encoding="utf-8"))})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
