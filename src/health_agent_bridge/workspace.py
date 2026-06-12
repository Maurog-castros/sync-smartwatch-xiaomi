from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AgentWorkspaceWriter:
    def __init__(self, workspace_path: Path) -> None:
        self.context_path = workspace_path / "context"

    def write_daily(
        self,
        markdown: str,
        alerts: list[dict[str, Any]],
        reminders: list[dict[str, Any]],
    ) -> dict[str, Path]:
        self.context_path.mkdir(parents=True, exist_ok=True)
        markdown_path = self.context_path / "health_today.md"
        alerts_path = self.context_path / "health_alerts.json"
        reminders_path = self.context_path / "reminders.json"

        markdown_path.write_text(markdown, encoding="utf-8")
        alerts_path.write_text(
            json.dumps(alerts, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        reminders_path.write_text(
            json.dumps(reminders, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

        return {
            "markdown": markdown_path,
            "alerts": alerts_path,
            "reminders": reminders_path,
        }
