from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .import_state import ImportState
from .repository import HealthRepository
from .whatsapp_sync_state import WhatsAppSyncState


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _hours_since(value: str | None) -> float | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    delta = datetime.now(parsed.tzinfo) - parsed
    return round(delta.total_seconds() / 3600, 1)


def build_health_coverage(
    *,
    repository: HealthRepository,
    user_name: str,
    import_state_path: Path,
    telegram_state_path: Path,
    pending_path: Path,
    timezone: str = "America/Santiago",
) -> dict[str, object]:
    import_state = ImportState.load(import_state_path, user_name)
    telegram_state = WhatsAppSyncState.load(telegram_state_path)
    latest_metric = repository.get_latest_rollup_date(user_name)
    pending = pending_path.exists()
    pending_data: dict[str, object] = {}
    if pending:
        try:
            pending_data = json.loads(pending_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pending_data = {"pending": True}

    last_import_at = import_state.last_import_at
    hours_since_import = _hours_since(last_import_at)
    data_stale = hours_since_import is None or hours_since_import > 36

    if pending:
        freshness = "Mauro anuncio que enviara el ZIP de Apple Health. Esperando archivo por Telegram."
    elif last_import_at is None:
        freshness = "Aun no hay import exitoso registrado."
    elif data_stale:
        freshness = (
            f"Ultimo import hace {hours_since_import} h. Los datos pueden estar desactualizados."
        )
    else:
        freshness = f"Ultimo import hace {hours_since_import} h. Datos recientes."

    return {
        "user_name": user_name,
        "timezone": timezone,
        "last_import_at": last_import_at,
        "last_metric_date": latest_metric.isoformat() if latest_metric else import_state.last_metric_date,
        "last_imported_days": import_state.last_imported_days,
        "last_export_source": "telegram",
        "last_export_filename": "exportar.zip",
        "last_telegram_file": telegram_state.last_message_label,
        "last_telegram_sync_at": telegram_state.last_sync_at,
        "export_pending": pending,
        "export_pending_details": pending_data,
        "hours_since_import": hours_since_import,
        "data_stale": data_stale,
        "freshness_summary": freshness,
        "agent_instructions": (
            "Si export_pending es true, Mauro ya aviso que enviara el ZIP: no pidas subirlo de nuevo. "
            "Si pregunta cuando fue el ultimo sync, usa last_import_at y freshness_summary. "
            "Si dice que ya lo envio, indica que el servidor lo procesa automaticamente en minutos."
        ),
    }


def write_health_coverage(
    *,
    repository: HealthRepository,
    user_name: str,
    storage_dir: Path,
    care_context_dir: Path,
    timezone: str = "America/Santiago",
    clear_pending: bool = False,
) -> Path:
    import_state_path = storage_dir / "import_state.json"
    telegram_state_path = storage_dir / "telegram_sync_state.json"
    pending_path = care_context_dir / "health_export_pending.json"
    if clear_pending and pending_path.exists():
        pending_path.unlink()

    coverage = build_health_coverage(
        repository=repository,
        user_name=user_name,
        import_state_path=import_state_path,
        telegram_state_path=telegram_state_path,
        pending_path=pending_path,
        timezone=timezone,
    )
    payload = json.dumps(coverage, ensure_ascii=True, indent=2)

    storage_dir.mkdir(parents=True, exist_ok=True)
    care_context_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / "health_coverage.json"
    context_path = care_context_dir / "health_coverage.json"
    storage_path.write_text(payload, encoding="utf-8")
    context_path.write_text(payload, encoding="utf-8")
    return context_path
