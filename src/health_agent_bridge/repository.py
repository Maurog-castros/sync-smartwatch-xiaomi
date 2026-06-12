from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .database import Database
from .schemas import HealthImportPayload


class HealthRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def import_payload(self, payload: HealthImportPayload) -> None:
        metric_date = payload.metric_date.isoformat()
        with self.database.connect() as connection:
            if payload.daily_metrics is not None:
                metrics = payload.daily_metrics
                connection.execute(
                    """
                    INSERT INTO daily_health_metrics (
                        user_name, metric_date, steps, distance_meters,
                        active_energy_kcal, exercise_minutes,
                        resting_heart_rate_bpm, average_heart_rate_bpm,
                        oxygen_saturation_percent, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_name, metric_date) DO UPDATE SET
                        steps = excluded.steps,
                        distance_meters = excluded.distance_meters,
                        active_energy_kcal = excluded.active_energy_kcal,
                        exercise_minutes = excluded.exercise_minutes,
                        resting_heart_rate_bpm = excluded.resting_heart_rate_bpm,
                        average_heart_rate_bpm = excluded.average_heart_rate_bpm,
                        oxygen_saturation_percent = excluded.oxygen_saturation_percent,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        payload.user_name,
                        metric_date,
                        metrics.steps,
                        metrics.distance_meters,
                        metrics.active_energy_kcal,
                        metrics.exercise_minutes,
                        metrics.resting_heart_rate_bpm,
                        metrics.average_heart_rate_bpm,
                        metrics.oxygen_saturation_percent,
                    ),
                )

            connection.execute(
                "DELETE FROM sleep_sessions WHERE user_name = ? AND metric_date = ?",
                (payload.user_name, metric_date),
            )
            connection.execute(
                "DELETE FROM activity_sessions WHERE user_name = ? AND metric_date = ?",
                (payload.user_name, metric_date),
            )
            connection.execute(
                "DELETE FROM wellness_notes WHERE user_name = ? AND metric_date = ?",
                (payload.user_name, metric_date),
            )

            connection.executemany(
                """
                INSERT INTO sleep_sessions (
                    user_name, metric_date, started_at, ended_at,
                    asleep_minutes, source
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        payload.user_name,
                        metric_date,
                        session.started_at.isoformat(),
                        session.ended_at.isoformat(),
                        session.asleep_minutes,
                        session.source,
                    )
                    for session in payload.sleep_sessions
                ],
            )
            connection.executemany(
                """
                INSERT INTO heart_rate_samples (user_name, sampled_at, bpm, source)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        payload.user_name,
                        sample.sampled_at.isoformat(),
                        sample.bpm,
                        sample.source,
                    )
                    for sample in payload.heart_rate_samples
                ],
            )
            connection.executemany(
                """
                INSERT INTO activity_sessions (
                    user_name, metric_date, activity_type, started_at, ended_at,
                    distance_meters, active_energy_kcal, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        payload.user_name,
                        metric_date,
                        session.activity_type,
                        session.started_at.isoformat(),
                        session.ended_at.isoformat(),
                        session.distance_meters,
                        session.active_energy_kcal,
                        session.source,
                    )
                    for session in payload.activity_sessions
                ],
            )
            connection.executemany(
                """
                INSERT INTO wellness_notes (
                    user_name, metric_date, noted_at, stress_level, body
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        payload.user_name,
                        metric_date,
                        note.noted_at.isoformat(),
                        note.stress_level,
                        note.body,
                    )
                    for note in payload.wellness_notes
                ],
            )

    def get_latest_rollup_date(self, user_name: str) -> date | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT MAX(metric_date) AS latest_date
                FROM daily_health_rollups
                WHERE user_name = ?
                """,
                (user_name,),
            ).fetchone()
        if row is None or row["latest_date"] is None:
            return None
        return date.fromisoformat(str(row["latest_date"]))

    def get_day_context(self, user_name: str, summary_date: date) -> dict[str, Any]:
        metric_date = summary_date.isoformat()
        week_start = (summary_date - timedelta(days=7)).isoformat()
        with self.database.connect() as connection:
            metrics = connection.execute(
                """
                SELECT * FROM daily_health_metrics
                WHERE user_name = ? AND metric_date = ?
                """,
                (user_name, metric_date),
            ).fetchone()
            rollup = connection.execute(
                """
                SELECT * FROM daily_health_rollups
                WHERE user_name = ? AND metric_date = ?
                """,
                (user_name, metric_date),
            ).fetchone()
            sleep = connection.execute(
                """
                SELECT COALESCE(SUM(asleep_minutes), 0) AS asleep_minutes
                FROM sleep_sessions
                WHERE user_name = ? AND metric_date = ?
                """,
                (user_name, metric_date),
            ).fetchone()
            notes = connection.execute(
                """
                SELECT stress_level, body FROM wellness_notes
                WHERE user_name = ? AND metric_date = ?
                ORDER BY noted_at ASC
                """,
                (user_name, metric_date),
            ).fetchall()
            week = connection.execute(
                """
                SELECT AVG(resting_heart_rate_bpm) AS avg_resting_hr
                FROM daily_health_metrics
                WHERE user_name = ?
                  AND metric_date < ?
                  AND metric_date >= ?
                  AND resting_heart_rate_bpm IS NOT NULL
                """,
                (user_name, metric_date, week_start),
            ).fetchone()

        rollup_sleep_minutes = rollup["sleep_minutes"] if rollup is not None else None
        session_sleep_minutes = int(sleep["asleep_minutes"] or 0)
        sleep_minutes = (
            session_sleep_minutes
            if session_sleep_minutes > 0
            else rollup_sleep_minutes
        )

        return {
            "metrics": dict(metrics) if metrics is not None else None,
            "rollup": dict(rollup) if rollup is not None else None,
            "sleep_minutes": sleep_minutes,
            "notes": [dict(note) for note in notes],
            "weekly_resting_hr": week["avg_resting_hr"],
        }

    def save_summary(
        self,
        user_name: str,
        summary_date: date,
        body_markdown: str,
        reminders: list[dict[str, str]],
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_summaries (
                    user_name, summary_date, summary_type, body_markdown
                ) VALUES (?, ?, 'daily', ?)
                """,
                (user_name, summary_date.isoformat(), body_markdown),
            )
            connection.execute(
                "DELETE FROM reminders WHERE user_name = ? AND reminder_date = ?",
                (user_name, summary_date.isoformat()),
            )
            connection.executemany(
                """
                INSERT INTO reminders (
                    user_name, reminder_date, category, body, severity
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        user_name,
                        summary_date.isoformat(),
                        reminder["category"],
                        reminder["body"],
                        reminder["severity"],
                    )
                    for reminder in reminders
                ],
            )
