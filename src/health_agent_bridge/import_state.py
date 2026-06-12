from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass
class ImportState:
    user_name: str
    last_export_path: str | None = None
    last_export_sha256: str | None = None
    last_export_size: int | None = None
    last_import_at: str | None = None
    last_metric_date: str | None = None
    last_imported_days: int = 0
    import_mode: str = "full"

    @classmethod
    def load(cls, path: Path, user_name: str) -> ImportState:
        if not path.exists():
            return cls(user_name=user_name)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("user_name") != user_name:
            return cls(user_name=user_name)
        return cls(**{**asdict(cls(user_name=user_name)), **data})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def touch_import(
        self,
        *,
        export_path: Path,
        export_sha256: str,
        export_size: int,
        last_metric_date: date | None,
        imported_days: int,
        import_mode: str,
    ) -> None:
        self.last_export_path = str(export_path)
        self.last_export_sha256 = export_sha256
        self.last_export_size = export_size
        self.last_import_at = datetime.now().astimezone().isoformat()
        self.last_metric_date = last_metric_date.isoformat() if last_metric_date else None
        self.last_imported_days = imported_days
        self.import_mode = import_mode
