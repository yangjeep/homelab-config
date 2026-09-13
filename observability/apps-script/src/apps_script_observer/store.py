from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from .aggregates import (
    LifetimeAggregate,
    LifetimeObservation,
    increment,
    initialize,
    lifetime_rows,
    successful_times,
)
from .errors import CollectionBoundExceededError
from .models import ExecutionKey, Process, StoredExecution

_TERMINAL = frozenset({"COMPLETED", "CANCELED", "FAILED", "TIMED_OUT"})
_PENDING_EVENTS_BOUND = "pending_events"


class Store(AbstractContextManager["Store"]):
    def __init__(self, path: Path, *, max_pending_events: int = 1_000) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._max_pending_events = max_pending_events
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS executions (
                execution_key TEXT PRIMARY KEY,
                script_alias TEXT NOT NULL,
                process_type TEXT NOT NULL,
                process_status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                duration_seconds REAL,
                terminal_counted INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS cursors (
                script_alias TEXT PRIMARY KEY,
                start_time TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
                execution_key TEXT PRIMARY KEY,
                script_alias TEXT NOT NULL,
                function_name TEXT NOT NULL,
                process_type TEXT NOT NULL,
                process_status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                duration_seconds REAL,
                emitted INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS collector_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                failures_total INTEGER NOT NULL DEFAULT 0,
                last_success_seconds REAL NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO collector_state(singleton) VALUES (1);
            """
        )
        initialize(self._connection)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._connection.close()

    def cursor(self, alias: str) -> datetime | None:
        row = self._connection.execute(
            "SELECT start_time FROM cursors WHERE script_alias = ?", (alias,)
        ).fetchone()
        return None if row is None else datetime.fromisoformat(row[0])

    def apply_batch(self, alias: str, processes: Sequence[Process], cursor_time: datetime) -> None:
        with self._connection:
            for process in processes:
                self._apply_process(alias, process)
            current = self.cursor(alias)
            effective = cursor_time if current is None or cursor_time > current else current
            self._connection.execute(
                "INSERT INTO cursors VALUES (?, ?) ON CONFLICT(script_alias) "
                "DO UPDATE SET start_time=excluded.start_time",
                (alias, effective.astimezone(UTC).isoformat()),
            )

    def _apply_process(self, alias: str, process: Process) -> None:
        key = _execution_key(alias, process)
        row = self._connection.execute(
            "SELECT process_status, duration_seconds, terminal_counted FROM executions "
            "WHERE execution_key = ?",
            (key,),
        ).fetchone()
        existing = (
            None
            if row is None
            else StoredExecution.model_validate(
                {"status": row[0], "duration_seconds": row[1], "terminal_counted": row[2]}
            )
        )
        counted = existing is not None and existing.terminal_counted
        terminal = process.process_status in _TERMINAL
        if terminal and not counted:
            pending_count = self._connection.execute(
                "SELECT COUNT(*) FROM outbox WHERE emitted = 0"
            ).fetchone()[0]
            if int(pending_count) >= self._max_pending_events:
                raise CollectionBoundExceededError(_PENDING_EVENTS_BOUND, self._max_pending_events)
        status = existing.status if counted and existing is not None else process.process_status
        duration = (
            existing.duration_seconds
            if counted and existing is not None
            else process.duration_seconds
        )
        self._connection.execute(
            """INSERT INTO executions VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(execution_key) DO UPDATE SET
              process_status=excluded.process_status,
              duration_seconds=excluded.duration_seconds,
              terminal_counted=MAX(executions.terminal_counted, excluded.terminal_counted)""",
            (
                key,
                alias,
                process.process_type,
                status,
                process.start_time.astimezone(UTC).isoformat(),
                duration,
                int(terminal or counted),
            ),
        )
        if terminal and not counted:
            self._connection.execute(
                "INSERT OR IGNORE INTO outbox VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                (
                    key,
                    alias,
                    process.function_name,
                    process.process_type,
                    process.process_status,
                    process.start_time.astimezone(UTC).isoformat(),
                    duration,
                ),
            )
            increment(
                self._connection,
                LifetimeObservation(
                    script_alias=alias,
                    process_type=process.process_type,
                    process_status=process.process_status,
                    start_time=process.start_time,
                    duration_seconds=duration,
                ),
            )

    def record_failure(self) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE collector_state SET failures_total = failures_total + 1 WHERE singleton = 1"
            )

    def mark_global_success(self, now: datetime) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE collector_state SET last_success_seconds = ? WHERE singleton = 1",
                (now.timestamp(),),
            )

    def oldest_pending(self, alias: str) -> datetime | None:
        row = self._connection.execute(
            "SELECT MIN(start_time) FROM executions WHERE script_alias = ? "
            "AND terminal_counted = 0",
            (alias,),
        ).fetchone()
        return None if row[0] is None else datetime.fromisoformat(row[0])

    def prune_pending(self, alias: str, cutoff: datetime) -> None:
        with self._connection:
            self._connection.execute(
                "DELETE FROM executions WHERE script_alias = ? AND terminal_counted = 0 "
                "AND start_time < ?",
                (alias, cutoff.astimezone(UTC).isoformat()),
            )

    def terminal_totals(self) -> dict[tuple[str, str, str], int]:
        return {
            (row.script_alias, row.process_type, row.process_status): row.executions_count
            for row in lifetime_rows(self._connection)
        }

    def duration_totals(self) -> dict[tuple[str, str, str], tuple[float, int]]:
        return {
            (row.script_alias, row.process_type, row.process_status): (
                row.duration_sum,
                row.duration_count,
            )
            for row in lifetime_rows(self._connection)
        }

    def metric_state(self) -> tuple[int, float]:
        row = self._connection.execute(
            "SELECT failures_total, last_success_seconds FROM collector_state WHERE singleton = 1"
        ).fetchone()
        return int(row[0]), float(row[1])

    def successful_execution_times(self) -> dict[str, float]:
        return successful_times(self._connection)

    def lifetime_aggregates(self) -> Iterator[LifetimeAggregate]:
        yield from lifetime_rows(self._connection)

    def terminal_observations_since(
        self, cutoff: datetime
    ) -> Iterator[tuple[str, str, str, float | None]]:
        yield from self._connection.execute(
            "SELECT script_alias, process_type, process_status, duration_seconds "
            "FROM executions WHERE terminal_counted = 1 AND start_time >= ?",
            (cutoff.astimezone(UTC).isoformat(),),
        )

    def pending_events(
        self, limit: int | None = None
    ) -> Iterator[tuple[str, str, str, str, str, str, float | None]]:
        effective_limit = self._max_pending_events if limit is None else limit
        yield from self._connection.execute(
            """SELECT execution_key, script_alias, function_name, process_type,
            process_status, start_time, duration_seconds FROM outbox WHERE emitted = 0
            ORDER BY start_time LIMIT ?""",
            (effective_limit,),
        )

    def mark_emitted(self, execution_key: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE outbox SET emitted = 1 WHERE execution_key = ?", (execution_key,)
            )

    def prune_terminal_detail(self, cutoff: datetime) -> None:
        cutoff_text = cutoff.astimezone(UTC).isoformat()
        with self._connection:
            self._connection.execute(
                """DELETE FROM executions WHERE terminal_counted = 1 AND start_time < ?
                AND NOT EXISTS (
                  SELECT 1 FROM outbox
                  WHERE outbox.execution_key = executions.execution_key AND emitted = 0
                )""",
                (cutoff_text,),
            )
            self._connection.execute(
                "DELETE FROM outbox WHERE emitted = 1 AND start_time < ?",
                (cutoff_text,),
            )


def _execution_key(alias: str, process: Process) -> ExecutionKey:
    value = (
        f"{alias}\0{process.function_name}\0{process.process_type}\0"
        f"{process.start_time.isoformat()}"
    )
    return ExecutionKey(hashlib.sha256(value.encode()).hexdigest())
