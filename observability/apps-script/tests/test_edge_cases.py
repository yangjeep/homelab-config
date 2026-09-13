from __future__ import annotations

import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from apps_script_observer.collector import Collector, Page
from apps_script_observer.errors import ApiError
from apps_script_observer.models import Process
from apps_script_observer.store import Store
from tests.test_collector import FakeApi, config, process


def test_terminal_state_survives_out_of_order_running_observation(tmp_path: Path) -> None:
    # Given a completed execution already counted in durable state.
    started = datetime(2026, 9, 13, 1, tzinfo=UTC)
    api = FakeApi({None: Page((process(status="COMPLETED", started=started),), None)})
    cfg = config(tmp_path)
    Collector(cfg, api, now=lambda: started + timedelta(hours=1), sleep=lambda _: None).run()

    # When an older RUNNING representation arrives out of order.
    api.pages[None] = Page((process(status="RUNNING", started=started),), None)
    Collector(cfg, api, now=lambda: started + timedelta(hours=2), sleep=lambda _: None).run()

    # Then the monotonic terminal counter remains in the completed series.
    with Store(cfg.state_path) as store:
        assert store.terminal_totals() == {("gmail-cleaner", "TIME_DRIVEN", "COMPLETED"): 1}


def test_pending_execution_extends_fetch_window_beyond_overlap(tmp_path: Path) -> None:
    # Given a running execution older than the normal ten-minute overlap.
    started = datetime(2026, 9, 13, 1, tzinfo=UTC)
    api = FakeApi({None: Page((process(status="RUNNING", started=started),), None)})
    cfg = config(tmp_path)
    Collector(cfg, api, now=lambda: started + timedelta(hours=1), sleep=lambda _: None).run()

    # When the next collection starts an hour later.
    Collector(cfg, api, now=lambda: started + timedelta(hours=2), sleep=lambda _: None).run()

    # Then the request window still includes the pending execution's start time.
    assert api.started_after_calls[-1] == started


def test_unknown_types_collapse_into_one_valid_prometheus_series(tmp_path: Path) -> None:
    # Given two terminal observations with different unknown process types.
    started = datetime(2026, 9, 13, 1, tzinfo=UTC)
    api = FakeApi(
        {
            None: Page(
                (
                    Process.model_validate(
                        {
                            "functionName": "runCleanup",
                            "processType": "NEW_TYPE",
                            "processStatus": "FAILED",
                            "startTime": started.isoformat(),
                            "duration": "1s",
                        }
                    ),
                    Process.model_validate(
                        {
                            "functionName": "previewCleanup",
                            "processType": "FUTURE_TYPE",
                            "processStatus": "FAILED",
                            "startTime": (started + timedelta(seconds=1)).isoformat(),
                            "duration": "2s",
                        }
                    ),
                ),
                None,
            )
        }
    )
    cfg = config(tmp_path)

    # When metrics are rendered.
    Collector(cfg, api, now=lambda: started + timedelta(hours=1), sleep=lambda _: None).run()
    metrics = cfg.metrics_path.read_text()

    # Then unknown values aggregate after normalization without duplicate samples.
    series = [
        line
        for line in metrics.splitlines()
        if line.startswith("homelab_apps_script_executions_terminal_total{")
    ]
    assert series == [
        (
            "homelab_apps_script_executions_terminal_total"
            '{script="gmail-cleaner",type="OTHER",status="FAILED"} 2'
        )
    ]


def test_invalid_duration_is_rejected_at_api_boundary() -> None:
    # Given a non-finite duration from an external response.
    payload = {
        "functionName": "runCleanup",
        "processType": "TIME_DRIVEN",
        "processStatus": "COMPLETED",
        "startTime": "2026-09-13T01:00:00Z",
        "duration": "NaNs",
    }

    # When the boundary model parses it, then validation fails.
    with pytest.raises(ValidationError):
        Process.model_validate(payload)


def test_metrics_file_is_world_readable_but_not_writable(tmp_path: Path) -> None:
    # Given a successful collection writing an atomic textfile.
    started = datetime(2026, 9, 13, 1, tzinfo=UTC)
    cfg = config(tmp_path)

    # When the metrics file replaces its temporary predecessor.
    Collector(
        cfg,
        FakeApi({None: Page((), None)}),
        now=lambda: started,
        sleep=lambda _: None,
    ).run()

    # Then node-exporter's separate user can read it and cannot modify it.
    assert stat.S_IMODE(cfg.metrics_path.stat().st_mode) == 0o644


def test_global_success_does_not_advance_after_later_script_failure(tmp_path: Path) -> None:
    # Given two configured scripts and a failure while fetching the second.
    base = config(tmp_path)
    cfg = replace(
        base,
        scripts=(
            type(base.scripts[0])("first", "first-id"),
            type(base.scripts[0])("second", "second-id"),
        ),
    )

    class SecondFailsApi:
        def fetch_page(
            self,
            *,
            script_id: str,
            started_after: datetime,
            page_token: str | None,
            page_size: int,
        ) -> Page:
            del started_after, page_token, page_size
            if script_id == "second-id":
                raise ApiError(status_code=503)
            return Page((), None)

    # When one collection run processes both scripts.
    result = Collector(
        cfg,
        SecondFailsApi(),
        now=lambda: datetime(2026, 9, 13, tzinfo=UTC),
        sleep=lambda _: None,
    ).run()

    # Then the global success timestamp remains unchanged.
    assert result.success is False
    with Store(cfg.state_path) as store:
        assert store.metric_state()[1] == 0


def test_failed_execution_does_not_create_success_timestamp(tmp_path: Path) -> None:
    # Given a successful poll that returns only a failed execution.
    started = datetime(2026, 9, 13, 1, tzinfo=UTC)
    cfg = config(tmp_path)

    # When collection and metric rendering complete normally.
    Collector(
        cfg,
        FakeApi({None: Page((process(status="FAILED", started=started),), None)}),
        now=lambda: started + timedelta(hours=1),
        sleep=lambda _: None,
    ).run()

    # Then collector freshness advances but execution success remains absent.
    metrics = cfg.metrics_path.read_text()
    collector_line = next(
        line
        for line in metrics.splitlines()
        if line.startswith("homelab_apps_script_collector_last_success_timestamp_seconds ")
    )
    assert float(collector_line.split()[1]) > 0
    assert 'homelab_apps_script_last_success_timestamp_seconds{script="' not in metrics


def test_rolling_metrics_include_only_executions_started_within_24_hours(
    tmp_path: Path,
) -> None:
    # Given terminal executions on both sides of the rolling 24-hour boundary.
    now = datetime(2026, 9, 13, 12, tzinfo=UTC)
    recent_success = process(status="COMPLETED", started=now - timedelta(hours=23), duration="12s")
    recent_failure = Process.model_validate(
        {
            "functionName": "runCleanup",
            "processType": "TIME_DRIVEN",
            "processStatus": "FAILED",
            "startTime": (now - timedelta(hours=1)).isoformat(),
            "duration": "42s",
        }
    )
    old_timeout = Process.model_validate(
        {
            "functionName": "runCleanup",
            "processType": "TIME_DRIVEN",
            "processStatus": "TIMED_OUT",
            "startTime": (now - timedelta(hours=25)).isoformat(),
            "duration": "120s",
        }
    )
    cfg = config(tmp_path)

    # When the collector renders its rolling gauges.
    Collector(
        cfg,
        FakeApi({None: Page((recent_success, recent_failure, old_timeout), None)}),
        now=lambda: now,
        sleep=lambda _: None,
    ).run()
    metrics = cfg.metrics_path.read_text()

    # Then recent status counts and the maximum exclude the older execution.
    assert (
        'homelab_apps_script_executions_last_24h{script="gmail-cleaner",'
        'type="TIME_DRIVEN",status="COMPLETED"} 1'
    ) in metrics
    assert (
        'homelab_apps_script_executions_last_24h{script="gmail-cleaner",'
        'type="TIME_DRIVEN",status="FAILED"} 1'
    ) in metrics
    assert (
        'homelab_apps_script_executions_last_24h{script="gmail-cleaner",'
        'type="TIME_DRIVEN",status="TIMED_OUT"}' not in metrics
    )
    assert (
        'homelab_apps_script_max_duration_seconds_last_24h{script="gmail-cleaner"} 42.000000'
    ) in metrics
