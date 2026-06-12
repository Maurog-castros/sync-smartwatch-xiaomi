from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .config import settings
from .database import Database
from .repository import HealthRepository
from .schemas import HealthImportPayload, ImportResult, SummaryResponse
from .summary_service import HealthSummaryService
from .workspace import AgentWorkspaceWriter

database = Database(settings.db_path)
repository = HealthRepository(database)
workspace_writer = AgentWorkspaceWriter(settings.workspace_path)
summary_service = HealthSummaryService(repository, workspace_writer)

app = FastAPI(
    title="Health Agent Bridge",
    version="0.1.0",
    description="Local health data bridge for Hermes/OpenClaw agent workspaces.",
)


@app.on_event("startup")
def initialize_database() -> None:
    database.initialize()


def require_api_key(x_api_key: str = Header(alias="X-API-Key")) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/health/import",
    response_model=ImportResult,
    dependencies=[Depends(require_api_key)],
)
def import_health(payload: HealthImportPayload) -> ImportResult:
    repository.import_payload(payload)
    return ImportResult(
        imported=True,
        metric_date=payload.metric_date,
        sleep_sessions=len(payload.sleep_sessions),
        heart_rate_samples=len(payload.heart_rate_samples),
        activity_sessions=len(payload.activity_sessions),
        wellness_notes=len(payload.wellness_notes),
    )


@app.get(
    "/health/summary/today",
    response_model=SummaryResponse,
    dependencies=[Depends(require_api_key)],
)
def get_today_summary() -> SummaryResponse:
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    summary = summary_service.generate_daily(settings.user_name, today)

    return SummaryResponse(
        user_name=settings.user_name,
        summary_date=today,
        markdown_path=str(summary.paths["markdown"]),
        alerts_path=str(summary.paths["alerts"]),
        reminders_path=str(summary.paths["reminders"]),
        summary=summary.markdown,
    )
