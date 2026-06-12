from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


StressLevel = Literal["low", "medium", "high"]


class DailyMetricsPayload(BaseModel):
    steps: int | None = Field(default=None, ge=0)
    distance_meters: float | None = Field(default=None, ge=0)
    active_energy_kcal: float | None = Field(default=None, ge=0)
    exercise_minutes: int | None = Field(default=None, ge=0)
    resting_heart_rate_bpm: int | None = Field(default=None, ge=20, le=220)
    average_heart_rate_bpm: int | None = Field(default=None, ge=20, le=220)
    oxygen_saturation_percent: float | None = Field(default=None, ge=50, le=100)


class SleepSessionPayload(BaseModel):
    started_at: datetime
    ended_at: datetime
    asleep_minutes: int = Field(ge=0, le=1440)
    source: str = Field(min_length=1, max_length=80)

    @field_validator("ended_at")
    @classmethod
    def validate_end_after_start(cls, ended_at: datetime, info: object) -> datetime:
        started_at = getattr(info, "data", {}).get("started_at")
        if started_at is not None and ended_at <= started_at:
            raise ValueError("ended_at must be after started_at")
        return ended_at


class HeartRateSamplePayload(BaseModel):
    sampled_at: datetime
    bpm: int = Field(ge=20, le=220)
    source: str = Field(min_length=1, max_length=80)


class ActivitySessionPayload(BaseModel):
    activity_type: str = Field(min_length=1, max_length=80)
    started_at: datetime
    ended_at: datetime
    distance_meters: float | None = Field(default=None, ge=0)
    active_energy_kcal: float | None = Field(default=None, ge=0)
    source: str = Field(min_length=1, max_length=80)

    @field_validator("ended_at")
    @classmethod
    def validate_end_after_start(cls, ended_at: datetime, info: object) -> datetime:
        started_at = getattr(info, "data", {}).get("started_at")
        if started_at is not None and ended_at <= started_at:
            raise ValueError("ended_at must be after started_at")
        return ended_at


class WellnessNotePayload(BaseModel):
    noted_at: datetime
    stress_level: StressLevel | None = None
    body: str = Field(min_length=1, max_length=2000)


class HealthImportPayload(BaseModel):
    user_name: str = Field(min_length=1, max_length=120)
    metric_date: date
    daily_metrics: DailyMetricsPayload | None = None
    sleep_sessions: list[SleepSessionPayload] = Field(default_factory=list)
    heart_rate_samples: list[HeartRateSamplePayload] = Field(default_factory=list)
    activity_sessions: list[ActivitySessionPayload] = Field(default_factory=list)
    wellness_notes: list[WellnessNotePayload] = Field(default_factory=list)


class ImportResult(BaseModel):
    imported: bool
    metric_date: date
    sleep_sessions: int
    heart_rate_samples: int
    activity_sessions: int
    wellness_notes: int


class SummaryResponse(BaseModel):
    user_name: str
    summary_date: date
    markdown_path: str
    alerts_path: str
    reminders_path: str
    summary: str
