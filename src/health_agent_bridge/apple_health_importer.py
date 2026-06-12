from __future__ import annotations

import argparse
import json
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import settings
from .database import Database
from .import_state import ImportState
from .repository import HealthRepository

DEFAULT_INCREMENTAL_OVERLAP_DAYS = 14


STEP_COUNT = "HKQuantityTypeIdentifierStepCount"
DISTANCE_WALKING_RUNNING = "HKQuantityTypeIdentifierDistanceWalkingRunning"
ACTIVE_ENERGY = "HKQuantityTypeIdentifierActiveEnergyBurned"
HEART_RATE = "HKQuantityTypeIdentifierHeartRate"
BODY_MASS = "HKQuantityTypeIdentifierBodyMass"
SLEEP_ANALYSIS = "HKCategoryTypeIdentifierSleepAnalysis"

ASLEEP_VALUES = {
    "HKCategoryValueSleepAnalysisAsleep",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
}

IN_BED_VALUES = {"HKCategoryValueSleepAnalysisInBed"}

DAY_NAMES = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


@dataclass
class DayAccumulator:
    sources: set[str] = field(default_factory=set)
    asleep_intervals: list[tuple[datetime, datetime]] = field(default_factory=list)
    in_bed_intervals: list[tuple[datetime, datetime]] = field(default_factory=list)
    steps: float = 0
    distance_meters: float = 0
    active_energy_kcal: float = 0
    heart_rate_sum: float = 0
    heart_rate_samples: int = 0
    heart_rate_min: int | None = None
    heart_rate_max: int | None = None
    weight_kg: float | None = None

    def add_heart_rate(self, bpm: float) -> None:
        bpm_int = round(bpm)
        self.heart_rate_sum += bpm
        self.heart_rate_samples += 1
        self.heart_rate_min = (
            bpm_int if self.heart_rate_min is None else min(self.heart_rate_min, bpm_int)
        )
        self.heart_rate_max = (
            bpm_int if self.heart_rate_max is None else max(self.heart_rate_max, bpm_int)
        )


@dataclass(frozen=True)
class ImportResult:
    imported_days: int
    start_date: date | None
    end_date: date | None
    import_mode: str
    skipped: bool = False
    skip_reason: str | None = None


class AppleHealthXmlImporter:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.repository = HealthRepository(database)

    def resolve_incremental_start(
        self,
        user_name: str,
        overlap_days: int = DEFAULT_INCREMENTAL_OVERLAP_DAYS,
    ) -> date | None:
        latest = self.repository.get_latest_rollup_date(user_name)
        if latest is None:
            return None
        return latest - timedelta(days=overlap_days)

    def import_xml(
        self,
        xml_path: Path,
        user_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
        replace: bool = True,
        incremental: bool = False,
        overlap_days: int = DEFAULT_INCREMENTAL_OVERLAP_DAYS,
    ) -> ImportResult:
        import_mode = "incremental" if incremental else "full"
        effective_start = start_date
        if incremental and effective_start is None:
            effective_start = self.resolve_incremental_start(user_name, overlap_days)

        self.database.initialize()
        rollups = self._parse_rollups(xml_path, effective_start, end_date)
        with self.database.connect() as connection:
            if replace:
                self._delete_existing(connection, user_name, effective_start, end_date)
            self._upsert_rollups(connection, user_name, rollups)
            self._sync_daily_metrics(connection, user_name, rollups)

        latest_imported = max(rollups) if rollups else None
        return ImportResult(
            imported_days=len(rollups),
            start_date=effective_start,
            end_date=end_date or latest_imported,
            import_mode=import_mode,
        )

    def import_export(
        self,
        export_path: Path,
        user_name: str,
        *,
        state_path: Path,
        incremental: bool = False,
        overlap_days: int = DEFAULT_INCREMENTAL_OVERLAP_DAYS,
        force: bool = False,
        end_date: date | None = None,
    ) -> ImportResult:
        from .export_archive import (  # noqa: PLC0415
            export_file_sha256,
            resolve_export_xml,
        )

        xml_path = resolve_export_xml(export_path)
        export_sha256 = export_file_sha256(export_path)
        export_size = export_path.stat().st_size
        state = ImportState.load(state_path, user_name)

        if (
            incremental
            and not force
            and state.last_export_sha256 == export_sha256
            and state.last_export_size == export_size
        ):
            return ImportResult(
                imported_days=0,
                start_date=None,
                end_date=None,
                import_mode="incremental",
                skipped=True,
                skip_reason="export_unchanged",
            )

        result = self.import_xml(
            xml_path=xml_path,
            user_name=user_name,
            end_date=end_date,
            replace=True,
            incremental=incremental,
            overlap_days=overlap_days,
        )
        if result.skipped:
            return result

        state.touch_import(
            export_path=export_path,
            export_sha256=export_sha256,
            export_size=export_size,
            last_metric_date=result.end_date,
            imported_days=result.imported_days,
            import_mode=result.import_mode,
        )
        state.save(state_path)
        return result

    def _parse_rollups(
        self,
        xml_path: Path,
        start_date: date | None,
        end_date: date | None,
    ) -> dict[date, DayAccumulator]:
        rollups: dict[date, DayAccumulator] = {}
        for _, element in ET.iterparse(xml_path, events=("end",)):
            if element.tag != "Record":
                element.clear()
                continue

            record_type = element.attrib.get("type", "")
            record_date = self._record_date(element, record_type)
            if record_date is None or not self._date_in_range(
                record_date,
                start_date,
                end_date,
            ):
                element.clear()
                continue

            day = rollups.setdefault(record_date, DayAccumulator())
            source = element.attrib.get("sourceName")
            if source:
                day.sources.add(source)
            self._apply_record(day, record_type, element.attrib)
            element.clear()

        return rollups

    def _apply_record(
        self,
        day: DayAccumulator,
        record_type: str,
        attributes: dict[str, str],
    ) -> None:
        value = attributes.get("value")
        if value is None:
            return

        if record_type == STEP_COUNT:
            day.steps += self._float_value(value)
        elif record_type == DISTANCE_WALKING_RUNNING:
            day.distance_meters += self._distance_to_meters(
                self._float_value(value),
                attributes.get("unit"),
            )
        elif record_type == ACTIVE_ENERGY:
            day.active_energy_kcal += self._energy_to_kcal(
                self._float_value(value),
                attributes.get("unit"),
            )
        elif record_type == HEART_RATE:
            day.add_heart_rate(self._float_value(value))
        elif record_type == BODY_MASS:
            day.weight_kg = self._weight_to_kg(
                self._float_value(value),
                attributes.get("unit"),
            )
        elif record_type == SLEEP_ANALYSIS and value in ASLEEP_VALUES:
            interval = self._interval(attributes)
            if interval is not None:
                day.asleep_intervals.append(interval)
        elif record_type == SLEEP_ANALYSIS and value in IN_BED_VALUES:
            interval = self._interval(attributes)
            if interval is not None:
                day.in_bed_intervals.append(interval)

    def _delete_existing(
        self,
        connection: sqlite3.Connection,
        user_name: str,
        start_date: date | None,
        end_date: date | None,
    ) -> None:
        params: list[object] = [user_name]
        where = "user_name = ?"
        if start_date is not None:
            where += " AND metric_date >= ?"
            params.append(start_date.isoformat())
        if end_date is not None:
            where += " AND metric_date <= ?"
            params.append(end_date.isoformat())

        connection.execute(f"DELETE FROM daily_health_rollups WHERE {where}", params)

    def _upsert_rollups(
        self,
        connection: sqlite3.Connection,
        user_name: str,
        rollups: dict[date, DayAccumulator],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO daily_health_rollups (
                user_name, metric_date, year, month, day_of_week, day_name,
                steps, distance_meters, active_energy_kcal, sleep_minutes,
                heart_rate_avg_bpm, heart_rate_min_bpm, heart_rate_max_bpm,
                heart_rate_samples, weight_kg, sources_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_name, metric_date) DO UPDATE SET
                year = excluded.year,
                month = excluded.month,
                day_of_week = excluded.day_of_week,
                day_name = excluded.day_name,
                steps = excluded.steps,
                distance_meters = excluded.distance_meters,
                active_energy_kcal = excluded.active_energy_kcal,
                sleep_minutes = excluded.sleep_minutes,
                heart_rate_avg_bpm = excluded.heart_rate_avg_bpm,
                heart_rate_min_bpm = excluded.heart_rate_min_bpm,
                heart_rate_max_bpm = excluded.heart_rate_max_bpm,
                heart_rate_samples = excluded.heart_rate_samples,
                weight_kg = excluded.weight_kg,
                sources_json = excluded.sources_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                self._rollup_row(user_name, metric_date, day)
                for metric_date, day in sorted(rollups.items())
            ],
        )

    def _sync_daily_metrics(
        self,
        connection: sqlite3.Connection,
        user_name: str,
        rollups: dict[date, DayAccumulator],
    ) -> None:
        connection.executemany(
            """
            INSERT INTO daily_health_metrics (
                user_name, metric_date, steps, distance_meters,
                active_energy_kcal, exercise_minutes,
                resting_heart_rate_bpm, average_heart_rate_bpm,
                oxygen_saturation_percent, updated_at
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(user_name, metric_date) DO UPDATE SET
                steps = excluded.steps,
                distance_meters = excluded.distance_meters,
                active_energy_kcal = excluded.active_energy_kcal,
                average_heart_rate_bpm = excluded.average_heart_rate_bpm,
                updated_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    user_name,
                    metric_date.isoformat(),
                    round(day.steps) if day.steps else None,
                    day.distance_meters or None,
                    day.active_energy_kcal or None,
                    self._heart_rate_avg(day),
                )
                for metric_date, day in sorted(rollups.items())
            ],
        )

    def _rollup_row(
        self,
        user_name: str,
        metric_date: date,
        day: DayAccumulator,
    ) -> tuple[object, ...]:
        return (
            user_name,
            metric_date.isoformat(),
            metric_date.year,
            metric_date.month,
            metric_date.weekday(),
            DAY_NAMES[metric_date.weekday()],
            round(day.steps) if day.steps else None,
            day.distance_meters or None,
            day.active_energy_kcal or None,
            round(self._sleep_minutes(day)) or None,
            self._heart_rate_avg(day),
            day.heart_rate_min,
            day.heart_rate_max,
            day.heart_rate_samples or None,
            day.weight_kg,
            json.dumps(sorted(day.sources), ensure_ascii=True),
        )

    def _heart_rate_avg(self, day: DayAccumulator) -> float | None:
        if day.heart_rate_samples == 0:
            return None
        return round(day.heart_rate_sum / day.heart_rate_samples, 2)

    def _sleep_minutes(self, day: DayAccumulator) -> float:
        intervals = day.asleep_intervals or day.in_bed_intervals
        if not intervals:
            return 0

        merged: list[tuple[datetime, datetime]] = []
        for start, end in sorted(intervals):
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
                continue
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))

        return sum((end - start).total_seconds() / 60 for start, end in merged)

    def _record_date(self, element: ET.Element, record_type: str) -> date | None:
        date_value = (
            element.attrib.get("endDate")
            if record_type == SLEEP_ANALYSIS
            else element.attrib.get("startDate")
        )
        if date_value is None:
            return None
        return self._parse_apple_datetime(date_value).date()

    def _interval(
        self,
        attributes: dict[str, str],
    ) -> tuple[datetime, datetime] | None:
        start = attributes.get("startDate")
        end = attributes.get("endDate")
        if start is None or end is None:
            return None
        started_at = self._parse_apple_datetime(start)
        ended_at = self._parse_apple_datetime(end)
        if ended_at <= started_at:
            return None
        return (started_at, ended_at)

    def _parse_apple_datetime(self, value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")

    def _date_in_range(
        self,
        value: date,
        start_date: date | None,
        end_date: date | None,
    ) -> bool:
        if start_date is not None and value < start_date:
            return False
        if end_date is not None and value > end_date:
            return False
        return True

    def _float_value(self, value: str) -> float:
        return float(value.replace(",", "."))

    def _distance_to_meters(self, value: float, unit: str | None) -> float:
        if unit == "km":
            return value * 1000
        if unit == "mi":
            return value * 1609.344
        return value

    def _energy_to_kcal(self, value: float, unit: str | None) -> float:
        if unit == "kJ":
            return value * 0.239005736
        return value

    def _weight_to_kg(self, value: float, unit: str | None) -> float:
        if unit in {"lb", "lbs"}:
            return value * 0.45359237
        return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Apple Health XML into local SQLite rollups.",
    )
    parser.add_argument("xml_path", type=Path, nargs="?")
    parser.add_argument("--user-name", default=settings.user_name)
    parser.add_argument("--db-path", type=Path, default=settings.db_path)
    parser.add_argument("--db-backend", default=settings.db_backend)
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--from-date", type=date.fromisoformat, default=None)
    parser.add_argument("--to-date", type=date.fromisoformat, default=None)
    parser.add_argument("--keep-existing", action="store_true")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Import only recent days based on the latest date in the database.",
    )
    parser.add_argument("--overlap-days", type=int, default=DEFAULT_INCREMENTAL_OVERLAP_DAYS)
    parser.add_argument("--export-zip", type=Path, default=None)
    parser.add_argument("--state-path", type=Path, default=Path("storage/import_state.json"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    database = Database(
        db_path=args.db_path,
        backend=args.db_backend,
        database_url=args.database_url,
    )
    importer = AppleHealthXmlImporter(database)

    if args.export_zip is not None:
        result = importer.import_export(
            export_path=args.export_zip,
            user_name=args.user_name,
            state_path=args.state_path,
            incremental=args.incremental,
            overlap_days=args.overlap_days,
            force=args.force,
            end_date=args.to_date,
        )
    else:
        if args.xml_path is None:
            raise SystemExit("Provide xml_path or --export-zip")
        result = importer.import_xml(
            xml_path=args.xml_path,
            user_name=args.user_name,
            start_date=args.from_date,
            end_date=args.to_date,
            replace=not args.keep_existing,
            incremental=args.incremental,
            overlap_days=args.overlap_days,
        )

    print(
        json.dumps(
            {
                "imported_days": result.imported_days,
                "skipped": result.skipped,
                "skip_reason": result.skip_reason,
                "import_mode": result.import_mode,
                "start_date": result.start_date.isoformat() if result.start_date else None,
                "end_date": result.end_date.isoformat() if result.end_date else None,
                "db_backend": args.db_backend,
                "db_path": str(args.db_path) if args.db_backend == "sqlite" else None,
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
