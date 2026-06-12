from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .repository import HealthRepository
from .workspace import AgentWorkspaceWriter


@dataclass(frozen=True)
class DailySummary:
    markdown: str
    alerts: list[dict[str, Any]]
    reminders: list[dict[str, str]]
    paths: dict[str, object]


class HealthSummaryService:
    LOW_SLEEP_MINUTES = 360
    LOW_STEPS = 3000
    HIGH_RESTING_HR_DELTA = 12

    def __init__(
        self,
        repository: HealthRepository,
        workspace_writer: AgentWorkspaceWriter,
    ) -> None:
        self.repository = repository
        self.workspace_writer = workspace_writer

    def generate_daily(self, user_name: str, summary_date: date) -> DailySummary:
        context = self.repository.get_day_context(user_name, summary_date)
        metrics = context["metrics"] or context["rollup"] or {}
        sleep_minutes = context["sleep_minutes"]
        alerts = self._build_alerts(metrics, sleep_minutes, context)
        reminders = self._build_reminders(metrics, sleep_minutes, context)
        markdown = self._build_markdown(
            user_name=user_name,
            summary_date=summary_date,
            metrics=metrics,
            sleep_minutes=sleep_minutes,
            alerts=alerts,
            reminders=reminders,
            notes=context["notes"],
        )
        paths = self.workspace_writer.write_daily(markdown, alerts, reminders)
        self.repository.save_summary(user_name, summary_date, markdown, reminders)

        return DailySummary(
            markdown=markdown,
            alerts=alerts,
            reminders=reminders,
            paths=paths,
        )

    def _build_alerts(
        self,
        metrics: dict[str, Any],
        sleep_minutes: int | None,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        steps = metrics.get("steps")
        resting_hr = metrics.get("resting_heart_rate_bpm")
        weekly_hr = context.get("weekly_resting_hr")
        stress_high = any(
            note["stress_level"] == "high" for note in context["notes"]
        )

        if sleep_minutes is not None and sleep_minutes < self.LOW_SLEEP_MINUTES:
            alerts.append(
                {
                    "category": "sleep",
                    "severity": "medium",
                    "message": "Sleep below 6 hours. Prefer recovery today.",
                }
            )
        if steps is not None and steps < self.LOW_STEPS:
            alerts.append(
                {
                    "category": "activity",
                    "severity": "low",
                    "message": "Low step count. Suggest gentle walking.",
                }
            )
        if (
            resting_hr is not None
            and weekly_hr is not None
            and resting_hr >= weekly_hr + self.HIGH_RESTING_HR_DELTA
        ):
            alerts.append(
                {
                    "category": "heart_rate",
                    "severity": "medium",
                    "message": "Resting heart rate is above recent baseline.",
                }
            )
        if sleep_minutes is not None and sleep_minutes < self.LOW_SLEEP_MINUTES and stress_high:
            alerts.append(
                {
                    "category": "recovery",
                    "severity": "medium",
                    "message": "Low sleep plus high stress note. Reduce load.",
                }
            )

        return alerts

    def _build_reminders(
        self,
        metrics: dict[str, Any],
        sleep_minutes: int | None,
        context: dict[str, Any],
    ) -> list[dict[str, str]]:
        reminders: list[dict[str, str]] = []
        steps = metrics.get("steps")
        stress_high = any(
            note["stress_level"] == "high" for note in context["notes"]
        )

        if sleep_minutes is not None and sleep_minutes < self.LOW_SLEEP_MINUTES:
            reminders.append(
                {
                    "category": "sleep",
                    "severity": "medium",
                    "body": "Dormir antes de las 23:30 y evitar pantalla tarde.",
                }
            )
        if steps is None or steps < self.LOW_STEPS:
            reminders.append(
                {
                    "category": "movement",
                    "severity": "low",
                    "body": "Caminar suave 20 minutos si no hay molestias.",
                }
            )
        if stress_high:
            reminders.append(
                {
                    "category": "stress",
                    "severity": "low",
                    "body": "Hacer pausa de respiracion de 3 minutos.",
                }
            )

        reminders.append(
            {
                "category": "hydration",
                "severity": "low",
                "body": "Tomar agua durante la jornada.",
            }
        )

        return reminders

    def _build_markdown(
        self,
        user_name: str,
        summary_date: date,
        metrics: dict[str, Any],
        sleep_minutes: int | None,
        alerts: list[dict[str, Any]],
        reminders: list[dict[str, str]],
        notes: list[dict[str, str | None]],
    ) -> str:
        sleep_label = (
            f"{sleep_minutes / 60:.1f} horas"
            if sleep_minutes is not None
            else "sin dato"
        )
        steps = metrics.get("steps", "sin dato")
        distance = metrics.get("distance_meters", "sin dato")
        resting_hr = metrics.get("resting_heart_rate_bpm", "sin dato")
        exercise = metrics.get("exercise_minutes", "sin dato")
        oxygen = metrics.get("oxygen_saturation_percent", "sin dato")

        alert_lines = [
            f"- [{alert['severity']}] {alert['category']}: {alert['message']}"
            for alert in alerts
        ] or ["- Sin alertas de habitos para hoy."]
        reminder_lines = [
            f"- [{reminder['severity']}] {reminder['body']}"
            for reminder in reminders
        ]
        note_lines = [
            f"- {note['stress_level'] or 'sin nivel'}: {note['body']}"
            for note in notes
        ] or ["- Sin notas manuales."]

        return "\n".join(
            [
                f"# Health Report - {summary_date.isoformat()}",
                "",
                f"Usuario: {user_name}",
                "",
                "## Biometrics",
                "",
                f"- Sueno: {sleep_label}",
                f"- Pasos: {steps}",
                f"- Distancia: {distance} metros",
                f"- Ejercicio: {exercise} minutos",
                f"- FC reposo: {resting_hr} bpm",
                f"- Oxigeno: {oxygen}%",
                "",
                "## Alerts",
                "",
                *alert_lines,
                "",
                "## Recommended Actions",
                "",
                *reminder_lines,
                "",
                "## Notes",
                "",
                *note_lines,
                "",
                "## Boundary",
                "",
                "No diagnosticar. Si un patron preocupante se repite o hay",
                "sintomas, recomendar consultar a un profesional de salud.",
                "",
            ]
        )
