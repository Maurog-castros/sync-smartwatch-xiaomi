from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HEALTH_BRIDGE_",
        extra="ignore",
    )

    api_key: str = "change-me-local-only"
    db_path: Path = Path("storage/health_agent_bridge.sqlite3")
    workspace_path: Path = Path("agent-workspace")
    user_name: str = "Mauro"
    timezone: str = "America/Santiago"


settings = Settings()
