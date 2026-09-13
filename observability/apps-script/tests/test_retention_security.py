from __future__ import annotations

import inspect
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from apps_script_observer.collector import Collector, Page
from apps_script_observer.config import RuntimeConfig, ScriptConfig
from apps_script_observer.errors import ApiError, CollectionBoundExceededError
from apps_script_observer.google_api import GoogleProcessesApi, create_client
from apps_script_observer.metrics import write_metrics
from apps_script_observer.store import Store
from tests.test_collector import FakeApi, config, process


def _create_legacy_database(
    path: Path, *, started: datetime, emitted: bool, cursor: datetime
) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE executions (
                execution_key TEXT PRIMARY KEY,
                script_alias TEXT NOT NULL,
                process_type TEXT NOT NULL,
                process_status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                duration_seconds REAL,
                terminal_counted INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE cursors (script_alias TEXT PRIMARY KEY, start_time TEXT NOT NULL);
            CREATE TABLE outbox (
                execution_key TEXT PRIMARY KEY,
                script_alias TEXT NOT NULL,
                function_name TEXT NOT NULL,
                process_type TEXT NOT NULL,
                process_status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                duration_seconds REAL,
                emitted INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE collector_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                failures_total INTEGER NOT NULL DEFAULT 0,
                last_success_seconds REAL NOT NULL DEFAULT 0
            );
            INSERT INTO collector_state(singleton) VALUES (1);
            """
        )
        values = (
            "legacy-key",
            "gmail-cleaner",
            "TIME_DRIVEN",
            "COMPLETED",
            started.isoformat(),
            12.5,
        )
        connection.execute("INSERT INTO executions VALUES (?, ?, ?, ?, ?, ?, 1)", values)
        connection.execute(
            "INSERT INTO outbox VALUES (?, ?, 'runCleanup', ?, ?, ?, ?, ?)",
            (*values[:2], *values[2:6], int(emitted)),
        )
        connection.execute(
            "INSERT INTO cursors VALUES (?, ?)",
            ("gmail-cleaner", cursor.isoformat()),
        )


def test_processes_api_endpoint_cannot_be_overridden_from_runtime() -> None:
    # Given the production runtime and Processes API constructors.
    runtime_fields = RuntimeConfig.model_fields
    api_parameters = inspect.signature(GoogleProcessesApi).parameters

    # When their configurable inputs are inspected, then neither exposes an API URL.
    assert "apps_script_api_url" not in runtime_fields
    assert "api_url" not in api_parameters


def test_processes_bearer_is_sent_only_to_official_endpoint() -> None:
    # Given a transport that records the destination receiving the OAuth bearer.
    destinations: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        destinations.append(str(request.url.copy_with(query=None)))
        assert request.headers["Authorization"] == "Bearer access-token"
        return httpx2.Response(200, json={"processes": []})

    # When the production adapter fetches a page through an injected test transport.
    with httpx2.Client(transport=httpx2.MockTransport(handler)) as client:
        GoogleProcessesApi(client=client, access_token="access-token").fetch_page(
            script_id="script-id",
            started_after=datetime(2026, 9, 13, tzinfo=UTC),
            page_token=None,
            page_size=50,
        )

    # Then the bearer reached only the exact official Processes endpoint.
    assert destinations == ["https://script.googleapis.com/v1/processes:listScriptProcesses"]
    with create_client() as production_client:
        assert production_client.follow_redirects is False


def test_legacy_database_migrates_once_and_prunes_detail_without_reset(
    tmp_path: Path,
) -> None:
    # Given one old terminal execution in the pre-aggregate database schema.
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    path = tmp_path / "legacy.sqlite3"
    _create_legacy_database(
        path,
        started=now - timedelta(days=31),
        emitted=True,
        cursor=now,
    )

    # When the database migrates, prunes delivered detail, and reopens.
    with Store(path) as store:
        store.prune_terminal_detail(now - timedelta(days=30))
        write_metrics(store, tmp_path / "metrics.prom", now=now)
    with Store(path) as reopened:
        totals = reopened.terminal_totals()
        successful = reopened.successful_execution_times()

    # Then lifetime counters, histogram, and last success remain monotonic exactly once.
    metrics = (tmp_path / "metrics.prom").read_text()
    assert totals == {("gmail-cleaner", "TIME_DRIVEN", "COMPLETED"): 1}
    expected_success = (now - timedelta(days=31)).timestamp() + 12.5
    assert abs(successful["gmail-cleaner"] - expected_success) < 0.000_001
    assert (
        'homelab_apps_script_execution_duration_seconds_count{script="gmail-cleaner",'
        'type="TIME_DRIVEN",status="COMPLETED"} 1'
    ) in metrics
    assert "homelab_apps_script_executions_last_24h{" not in metrics
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


def test_prune_preserves_undelivered_outbox_and_execution(tmp_path: Path) -> None:
    # Given old terminal detail whose journal event has not been delivered.
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    path = tmp_path / "pending-outbox.sqlite3"
    _create_legacy_database(
        path,
        started=now - timedelta(days=31),
        emitted=False,
        cursor=now,
    )

    # When detail retention runs.
    with Store(path) as store:
        store.prune_terminal_detail(now - timedelta(days=30))
        pending = tuple(store.pending_events())

    # Then neither the event nor its dedupe detail is silently dropped.
    assert len(pending) == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1


def test_prune_removes_old_terminal_detail_without_an_outbox_row(tmp_path: Path) -> None:
    # Given migrated terminal detail whose historical outbox row is already absent.
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    path = tmp_path / "orphan-detail.sqlite3"
    _create_legacy_database(
        path,
        started=now - timedelta(days=31),
        emitted=True,
        cursor=now,
    )
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM outbox")

    # When detail retention runs, then orphaned terminal detail is still bounded.
    with Store(path) as store:
        store.prune_terminal_detail(now - timedelta(days=30))
        assert sum(store.terminal_totals().values()) == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 0


def test_outbox_capacity_rolls_back_new_batch(tmp_path: Path) -> None:
    # Given a store capped at one pending event and a two-terminal batch.
    started = datetime(2026, 9, 13, 1, tzinfo=UTC)
    processes = (
        process(status="COMPLETED", started=started),
        process(status="FAILED", started=started + timedelta(seconds=1)),
    )

    # When applying the batch would exceed the durable outbox capacity.
    with Store(tmp_path / "state.sqlite3", max_pending_events=1) as store:
        with pytest.raises(CollectionBoundExceededError):
            store.apply_batch("gmail-cleaner", processes, started + timedelta(hours=1))

        # Then the whole batch and cursor are rolled back instead of dropping an event.
        assert store.terminal_totals() == {}
        assert tuple(store.pending_events()) == ()
        assert store.cursor("gmail-cleaner") is None


def test_collector_emission_budget_preserves_new_pending_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given a legacy pending event consuming a one-event per-run emission budget.
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    cfg = replace(config(tmp_path), max_pending_events=1)
    _create_legacy_database(
        cfg.state_path,
        started=now - timedelta(hours=1),
        emitted=False,
        cursor=now,
    )
    new_process = process(status="FAILED", started=now + timedelta(minutes=1))

    # When collection drains the old event and observes a new terminal event.
    first = Collector(
        cfg,
        FakeApi({None: Page((new_process,), None)}),
        now=lambda: now + timedelta(hours=1),
        sleep=lambda _: None,
    ).run()
    first_output = capsys.readouterr().out

    # Then only one event is emitted and the new event remains durably pending.
    assert first.success is True
    assert first_output.count('"event":"apps_script.execution_terminal"') == 1
    with Store(cfg.state_path, max_pending_events=1) as store:
        assert len(tuple(store.pending_events())) == 1
        assert sum(store.terminal_totals().values()) == 2


def test_pruned_history_stays_outside_incremental_fetch_window(tmp_path: Path) -> None:
    # Given migrated old detail, a current cursor, and one delivered event.
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    cfg = config(tmp_path)
    _create_legacy_database(
        cfg.state_path,
        started=now - timedelta(days=31),
        emitted=True,
        cursor=now,
    )
    api = FakeApi({None: Page((), None)})

    # When the next incremental collection runs after detail was retired.
    Collector(cfg, api, now=lambda: now + timedelta(hours=1), sleep=lambda _: None).run()

    # Then it requests only the cursor overlap and does not reopen old history.
    assert api.started_after_calls == [now - cfg.overlap]
    with Store(cfg.state_path) as store:
        assert store.terminal_totals() == {("gmail-cleaner", "TIME_DRIVEN", "COMPLETED"): 1}
    with sqlite3.connect(cfg.state_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 0


def test_partial_failures_still_prune_delivered_terminal_detail(tmp_path: Path) -> None:
    # Given two scripts where the first commits a terminal result and the second always fails.
    cfg = replace(
        config(tmp_path),
        scripts=(
            ScriptConfig(alias="first", script_id="first-id"),
            ScriptConfig(alias="second", script_id="second-id"),
        ),
        max_pending_events=1,
    )
    base = datetime(2026, 1, 1, tzinfo=UTC)

    class PartialFailureApi:
        def __init__(self, started: datetime) -> None:
            self._process = process(status="COMPLETED", started=started)

        def fetch_page(
            self,
            *,
            script_id: str,
            started_after: datetime,
            page_token: str | None,
            page_size: int,
        ) -> Page:
            del started_after, page_token, page_size
            if script_id == "first-id":
                return Page((self._process,), None)
            raise ApiError(status_code=503)

    # When partial failures recur beyond the 30-day detail retention horizon.
    for index in range(6):
        current = base + timedelta(days=31 * index)
        result = Collector(
            cfg,
            PartialFailureApi(current - timedelta(minutes=1)),
            now=lambda current=current: current,
            sleep=lambda _: None,
        ).run()
        assert result.success is False

    # Then delivered detail stays bounded while lifetime counts and one pending event remain.
    with sqlite3.connect(cfg.state_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM outbox WHERE emitted = 0").fetchone()[0] == 1
        )
    with Store(cfg.state_path, max_pending_events=1) as store:
        assert sum(store.terminal_totals().values()) == 6
        assert store.metric_state() == (6, 0.0)
