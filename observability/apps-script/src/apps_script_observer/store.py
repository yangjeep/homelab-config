from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from .models import CompletedExecution, ExecutionKey, Process, StoredExecution

_TERMINAL = frozenset({"COMPLETED", "CANCELED", "FAILED", "TIMED_OUT"})


class Store(AbstractContextManager["Store"]):
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
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
        rows = self._connection.execute(
            """SELECT script_alias, process_type, process_status, COUNT(*)
            FROM executions WHERE terminal_counted = 1 GROUP BY 1, 2, 3"""
        )
        return {(row[0], row[1], row[2]): row[3] for row in rows}

    def duration_totals(self) -> dict[tuple[str, str, str], tuple[float, int]]:
        rows = self._connection.execute(
            """SELECT script_alias, process_type, process_status,
            COALESCE(SUM(duration_seconds), 0), COUNT(duration_seconds)
            FROM executions WHERE terminal_counted = 1 GROUP BY 1, 2, 3"""
        )
        return {(row[0], row[1], row[2]): (float(row[3]), int(row[4])) for row in rows}

    def metric_state(self) -> tuple[int, float]:
        row = self._connection.execute(
            "SELECT failures_total, last_success_seconds FROM collector_state WHERE singleton = 1"
        ).fetchone()
        return int(row[0]), float(row[1])

    def successful_execution_times(self) -> dict[str, float]:
        rows = self._connection.execute(
            "SELECT script_alias, start_time, duration_seconds FROM executions "
            "WHERE terminal_counted = 1 AND process_status = 'COMPLETED'"
        )
        latest: dict[str, float] = {}
        for row in rows:
            execution = CompletedExecution.model_validate(
                {
                    "script_alias": row[0],
                    "start_time": row[1],
                    "duration_seconds": row[2],
                }
            )
            completed = execution.start_time.timestamp() + (execution.duration_seconds or 0.0)
            latest[execution.script_alias] = max(
                completed, latest.get(execution.script_alias, completed)
            )
        return latest

    def terminal_observations(self) -> Iterator[tuple[str, str, str, float | None]]:
        yield from self._connection.execute(
            "SELECT script_alias, process_type, process_status, duration_seconds "
            "FROM executions WHERE terminal_counted = 1"
        )

    def terminal_observations_since(
        self, cutoff: datetime
    ) -> Iterator[tuple[str, str, str, float | None]]:
        yield from self._connection.execute(
            "SELECT script_alias, process_type, process_status, duration_seconds "
            "FROM executions WHERE terminal_counted = 1 AND start_time >= ?",
            (cutoff.astimezone(UTC).isoformat(),),
        )

    def pending_events(self) -> Iterator[tuple[str, str, str, str, str, str, float | None]]:
        yield from self._connection.execute(
            """SELECT execution_key, script_alias, function_name, process_type,
            process_status, start_time, duration_seconds FROM outbox WHERE emitted = 0"""
        )

    def mark_emitted(self, execution_key: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE outbox SET emitted = 1 WHERE execution_key = ?", (execution_key,)
            )


def _execution_key(alias: str, process: Process) -> ExecutionKey:
    value = (
        f"{alias}\0{process.function_name}\0{process.process_type}\0"
        f"{process.start_time.isoformat()}"
    )
    return ExecutionKey(hashlib.sha256(value.encode()).hexdigest())
