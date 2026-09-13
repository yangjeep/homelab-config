from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Final

ALLOWED_TYPES: Final = frozenset(
    {"ADD_ON", "EXECUTION_API", "TIME_DRIVEN", "TRIGGER", "WEBAPP", "EDITOR"}
)
ALLOWED_STATUSES: Final = frozenset({"COMPLETED", "CANCELED", "FAILED", "TIMED_OUT"})
DURATION_BUCKETS: Final = (0.1, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0, 3600.0)
_MIGRATION: Final = "lifetime_aggregates_v1"


@dataclass(frozen=True, slots=True)
class LifetimeAggregate:
    script_alias: str
    process_type: str
    process_status: str
    executions_count: int
    duration_sum: float
    duration_count: int
    bucket_counts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class LifetimeObservation:
    script_alias: str
    process_type: str
    process_status: str
    start_time: datetime
    duration_seconds: float | None


def initialize(connection: sqlite3.Connection) -> None:
    with connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS lifetime_execution_aggregates (
                script_alias TEXT NOT NULL,
                process_type TEXT NOT NULL,
                process_status TEXT NOT NULL,
                executions_count INTEGER NOT NULL,
                duration_sum REAL NOT NULL,
                duration_count INTEGER NOT NULL,
                PRIMARY KEY (script_alias, process_type, process_status)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS lifetime_duration_buckets (
                script_alias TEXT NOT NULL,
                process_type TEXT NOT NULL,
                process_status TEXT NOT NULL,
                bucket_upper REAL NOT NULL,
                observations_count INTEGER NOT NULL,
                PRIMARY KEY (script_alias, process_type, process_status, bucket_upper)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS script_success_aggregates (
                script_alias TEXT PRIMARY KEY,
                last_success_seconds REAL NOT NULL
            )"""
        )
        migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE name = ?", (_MIGRATION,)
        ).fetchone()
        if migrated is not None:
            return
        connection.execute("DELETE FROM lifetime_execution_aggregates")
        connection.execute("DELETE FROM lifetime_duration_buckets")
        connection.execute("DELETE FROM script_success_aggregates")
        rows = connection.execute(
            "SELECT script_alias, process_type, process_status, start_time, duration_seconds "
            "FROM executions WHERE terminal_counted = 1"
        )
        for alias, process_type, status, start_time, duration in rows:
            increment(
                connection,
                LifetimeObservation(
                    script_alias=str(alias),
                    process_type=str(process_type),
                    process_status=str(status),
                    start_time=datetime.fromisoformat(str(start_time)),
                    duration_seconds=None if duration is None else float(duration),
                ),
            )
        connection.execute("INSERT INTO schema_migrations(name) VALUES (?)", (_MIGRATION,))


def increment(
    connection: sqlite3.Connection,
    observation: LifetimeObservation,
) -> None:
    safe_type = observation.process_type if observation.process_type in ALLOWED_TYPES else "OTHER"
    safe_status = (
        observation.process_status if observation.process_status in ALLOWED_STATUSES else "OTHER"
    )
    duration_sum = observation.duration_seconds or 0.0
    duration_count = int(observation.duration_seconds is not None)
    labels = (observation.script_alias, safe_type, safe_status)
    connection.execute(
        """INSERT INTO lifetime_execution_aggregates
        VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(script_alias, process_type, process_status) DO UPDATE SET
          executions_count=executions_count + 1,
          duration_sum=duration_sum + excluded.duration_sum,
          duration_count=duration_count + excluded.duration_count""",
        (*labels, duration_sum, duration_count),
    )
    if observation.duration_seconds is not None:
        for bucket in DURATION_BUCKETS:
            if observation.duration_seconds <= bucket:
                connection.execute(
                    """INSERT INTO lifetime_duration_buckets VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(script_alias, process_type, process_status, bucket_upper)
                    DO UPDATE SET observations_count=observations_count + 1""",
                    (*labels, bucket),
                )
    if safe_status == "COMPLETED":
        completed = observation.start_time.timestamp() + duration_sum
        connection.execute(
            """INSERT INTO script_success_aggregates VALUES (?, ?)
            ON CONFLICT(script_alias) DO UPDATE SET
              last_success_seconds=MAX(last_success_seconds, excluded.last_success_seconds)""",
            (observation.script_alias, completed),
        )


def lifetime_rows(connection: sqlite3.Connection) -> Iterator[LifetimeAggregate]:
    rows = connection.execute(
        """SELECT script_alias, process_type, process_status,
        executions_count, duration_sum, duration_count
        FROM lifetime_execution_aggregates ORDER BY 1, 2, 3"""
    )
    for alias, process_type, status, count, duration_sum, duration_count in rows:
        bucket_counts = tuple(
            _bucket_count(
                connection,
                (str(alias), str(process_type), str(status)),
                bucket,
            )
            for bucket in DURATION_BUCKETS
        )
        yield LifetimeAggregate(
            script_alias=str(alias),
            process_type=str(process_type),
            process_status=str(status),
            executions_count=int(count),
            duration_sum=float(duration_sum),
            duration_count=int(duration_count),
            bucket_counts=bucket_counts,
        )


def successful_times(connection: sqlite3.Connection) -> dict[str, float]:
    rows = connection.execute(
        "SELECT script_alias, last_success_seconds FROM script_success_aggregates"
    )
    return {str(alias): float(timestamp) for alias, timestamp in rows}


def _bucket_count(
    connection: sqlite3.Connection,
    labels: tuple[str, str, str],
    bucket: float,
) -> int:
    row = connection.execute(
        """SELECT observations_count FROM lifetime_duration_buckets
        WHERE script_alias = ? AND process_type = ? AND process_status = ? AND bucket_upper = ?""",
        (*labels, bucket),
    ).fetchone()
    return 0 if row is None else int(row[0])
