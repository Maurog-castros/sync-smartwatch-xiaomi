from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS daily_health_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    steps INTEGER,
    distance_meters REAL,
    active_energy_kcal REAL,
    exercise_minutes INTEGER,
    resting_heart_rate_bpm INTEGER,
    average_heart_rate_bpm INTEGER,
    oxygen_saturation_percent REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_name, metric_date)
);

CREATE TABLE IF NOT EXISTS daily_health_rollups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name TEXT NOT NULL,
    steps INTEGER,
    distance_meters REAL,
    active_energy_kcal REAL,
    sleep_minutes INTEGER,
    heart_rate_avg_bpm REAL,
    heart_rate_min_bpm INTEGER,
    heart_rate_max_bpm INTEGER,
    heart_rate_samples INTEGER,
    weight_kg REAL,
    sources_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_name, metric_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_health_rollups_user_date
ON daily_health_rollups(user_name, metric_date);

CREATE INDEX IF NOT EXISTS idx_daily_health_rollups_calendar
ON daily_health_rollups(user_name, year, month, day_of_week);

CREATE TABLE IF NOT EXISTS sleep_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    asleep_minutes INTEGER NOT NULL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS heart_rate_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    sampled_at TEXT NOT NULL,
    bpm INTEGER NOT NULL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    distance_meters REAL,
    active_energy_kcal REAL,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wellness_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    noted_at TEXT NOT NULL,
    stress_level TEXT,
    body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    summary_date TEXT NOT NULL,
    summary_type TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT NOT NULL,
    reminder_date TEXT NOT NULL,
    category TEXT NOT NULL,
    body TEXT NOT NULL,
    severity TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


POSTGRES_SCHEMA = SQLITE_SCHEMA.replace(
    "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "id BIGSERIAL PRIMARY KEY",
).replace("PRAGMA foreign_keys = ON;", "")


class DatabaseConnection:
    def __init__(self, connection: Any, backend: str) -> None:
        self.connection = connection
        self.backend = backend

    def executescript(self, script: str) -> None:
        if self.backend == "sqlite":
            self.connection.executescript(script)
            return

        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def execute(
        self,
        sql: str,
        params: tuple[object, ...] | list[object] = (),
    ) -> Any:
        return self.connection.execute(self._prepare(sql), params)

    def executemany(
        self,
        sql: str,
        params: list[tuple[object, ...]],
    ) -> None:
        if not params:
            return
        if self.backend == "sqlite":
            self.connection.executemany(sql, params)
            return
        with self.connection.cursor() as cursor:
            cursor.executemany(self._prepare(sql), params)

    def _prepare(self, sql: str) -> str:
        if self.backend == "postgres":
            return sql.replace("?", "%s")
        return sql


class Database:
    def __init__(
        self,
        db_path: Path,
        backend: str = "sqlite",
        database_url: str | None = None,
    ) -> None:
        self.db_path = db_path
        self.backend = backend
        self.database_url = database_url

    def initialize(self) -> None:
        if self.backend == "sqlite":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                POSTGRES_SCHEMA if self.backend == "postgres" else SQLITE_SCHEMA
            )

    @contextmanager
    def connect(self) -> Iterator[DatabaseConnection]:
        connection = self._open_connection()
        try:
            yield DatabaseConnection(connection, self.backend)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _open_connection(self) -> Any:
        if self.backend == "sqlite":
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            return connection

        if self.backend == "postgres":
            if not self.database_url:
                raise ValueError("database_url is required for postgres backend")
            return psycopg.connect(self.database_url, row_factory=dict_row)

        raise ValueError(f"Unsupported database backend: {self.backend}")
