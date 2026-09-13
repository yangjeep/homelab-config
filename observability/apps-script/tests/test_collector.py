from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from apps_script_observer.collector import Collector, Page, RateLimited
from apps_script_observer.config import CollectorConfig, ScriptConfig
from apps_script_observer.models import Process
from apps_script_observer.store import Store


def process(*, status: str, started: datetime, duration: str = "1.5s") -> Process:
    return Process.model_validate(
        {
            "functionName": "runCleanup",
            "processType": "TIME_DRIVEN",
            "processStatus": status,
            "startTime": started.isoformat().replace("+00:00", "Z"),
            "duration": duration,
        }
    )


class FakeApi:
    def __init__(self, pages: dict[str | None, Page | RateLimited]) -> None:
        self.pages = pages
        self.calls: list[str | None] = []
        self.started_after_calls: list[datetime] = []

    def fetch_page(
        self,
        *,
        script_id: str,
        started_after: datetime,
        page_token: str | None,
        page_size: int,
    ) -> Page:
        del script_id, page_size
        self.calls.append(page_token)
        self.started_after_calls.append(started_after)
        result = self.pages[page_token]
        if isinstance(result, RateLimited):
            self.pages[page_token] = Page(processes=(), next_page_token=None)
            raise result
        return result


def config(tmp_path: Path, *, max_records: int = 100) -> CollectorConfig:
    return CollectorConfig(
        scripts=(ScriptConfig(alias="gmail-cleaner", script_id="script-id"),),
        state_path=tmp_path / "state.sqlite3",
        metrics_path=tmp_path / "apps_script.prom",
        initial_lookback=timedelta(days=7),
        overlap=timedelta(minutes=10),
        page_size=50,
        max_pages=4,
        max_records=max_records,
        max_rate_limit_retries=2,
        max_retry_after=timedelta(seconds=2),
    )


def test_terminal_transition_is_counted_once_after_restart(tmp_path: Path) -> None:
    # Given an execution first observed while running.
    started = datetime(2026, 9, 13, 1, tzinfo=UTC)
    api = FakeApi({None: Page((process(status="RUNNING", started=started),), None)})
    cfg = config(tmp_path)
    Collector(cfg, api, now=lambda: started + timedelta(hours=1), sleep=lambda _: None).run()

    # When a new collector process sees it complete twice.
    api.pages[None] = Page((process(status="COMPLETED", started=started),), None)
    Collector(cfg, api, now=lambda: started + timedelta(hours=2), sleep=lambda _: None).run()
    Collector(cfg, api, now=lambda: started + timedelta(hours=3), sleep=lambda _: None).run()

    # Then the durable aggregate contains one completion.
    with Store(cfg.state_path) as store:
        assert store.terminal_totals() == {("gmail-cleaner", "TIME_DRIVEN", "COMPLETED"): 1}


def test_all_pages_commit_one_cursor_after_complete_pagination(tmp_path: Path) -> None:
    # Given two API pages with increasing start times.
    first = datetime(2026, 9, 13, 1, tzinfo=UTC)
    second = first + timedelta(minutes=5)
    api = FakeApi(
        {
            None: Page((process(status="COMPLETED", started=first),), "next"),
            "next": Page((process(status="FAILED", started=second),), None),
        }
    )
    cfg = config(tmp_path)

    # When collection completes.
    Collector(cfg, api, now=lambda: second + timedelta(hours=1), sleep=lambda _: None).run()

    # Then both pages are processed and the cursor advances to the newest record.
    assert api.calls == [None, "next"]
    with Store(cfg.state_path) as store:
        assert store.cursor("gmail-cleaner") == second + timedelta(hours=1)


def test_record_bound_aborts_without_advancing_cursor(tmp_path: Path) -> None:
    # Given a page larger than the configured collection bound.
    started = datetime(2026, 9, 13, 1, tzinfo=UTC)
    api = FakeApi(
        {
            None: Page(
                tuple(
                    process(status="COMPLETED", started=started + timedelta(seconds=i))
                    for i in range(3)
                ),
                None,
            )
        }
    )
    cfg = config(tmp_path, max_records=2)

    # When collection exceeds the bound.
    result = Collector(
        cfg, api, now=lambda: started + timedelta(hours=1), sleep=lambda _: None
    ).run()

    # Then the run fails and no partial observations or cursor are committed.
    assert result.success is False
    with Store(cfg.state_path) as store:
        assert store.cursor("gmail-cleaner") is None
        assert store.terminal_totals() == {}


def test_rate_limit_retry_is_bounded(tmp_path: Path) -> None:
    # Given an API that rate limits the first request.
    api = FakeApi({None: RateLimited(retry_after_seconds=10.0)})
    sleeps: list[float] = []
    cfg = config(tmp_path)

    # When the collector retries.
    result = Collector(
        cfg, api, now=lambda: datetime(2026, 9, 13, tzinfo=UTC), sleep=sleeps.append
    ).run()

    # Then Retry-After is capped and the successful retry completes.
    assert result.success is True
    assert sleeps == [2.0]
    assert api.calls == [None, None]


def test_terminal_event_is_not_logged_again_after_restart(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Given one completed execution observed by a collector run.
    started = datetime(2026, 9, 13, 1, tzinfo=UTC)
    api = FakeApi({None: Page((process(status="COMPLETED", started=started),), None)})
    cfg = config(tmp_path)
    first = Collector(cfg, api, now=lambda: started + timedelta(hours=1), sleep=lambda _: None)
    first.run()
    first_output = capsys.readouterr()

    # When the same execution is observed after a process restart.
    second = Collector(cfg, api, now=lambda: started + timedelta(hours=2), sleep=lambda _: None)
    second.run()
    second_output = capsys.readouterr()

    # Then its idempotency key is logged once and the retry produces no duplicate event.
    assert first_output.out.count('"event":"apps_script.execution_terminal"') == 1
    assert second_output.out == ""


def test_exhausted_rate_limit_updates_failure_metric(tmp_path: Path) -> None:
    # Given an API that remains rate limited beyond the retry budget.
    class AlwaysLimitedApi:
        def fetch_page(
            self,
            *,
            script_id: str,
            started_after: datetime,
            page_token: str | None,
            page_size: int,
        ) -> Page:
            del script_id, started_after, page_token, page_size
            raise RateLimited(retry_after_seconds=0)

    cfg = config(tmp_path)

    # When the retry budget is exhausted.
    result = Collector(
        cfg,
        AlwaysLimitedApi(),
        now=lambda: datetime(2026, 9, 13, tzinfo=UTC),
        sleep=lambda _: None,
    ).run()

    # Then the run fails and the durable failure counter is exposed to node-exporter.
    assert result.success is False
    assert "homelab_apps_script_collector_failures_total 1" in cfg.metrics_path.read_text()
