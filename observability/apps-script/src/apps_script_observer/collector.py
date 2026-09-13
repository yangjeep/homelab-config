from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .config import CollectorConfig, ScriptConfig
from .errors import (
    ApiError,
    CollectionBoundExceededError,
    RateLimitedError,
    ResponseTooLargeError,
)
from .metrics import write_metrics
from .models import Process
from .store import Store


@dataclass(frozen=True, slots=True)
class Page:
    processes: Sequence[Process]
    next_page_token: str | None


@dataclass(frozen=True, slots=True)
class CollectionResult:
    success: bool
    records: int


class ProcessesApi(Protocol):
    def fetch_page(
        self,
        *,
        script_id: str,
        started_after: datetime,
        page_token: str | None,
        page_size: int,
    ) -> Page: ...


class Collector:
    def __init__(
        self,
        config: CollectorConfig,
        api: ProcessesApi,
        *,
        now: Callable[[], datetime],
        sleep: Callable[[float], None],
    ) -> None:
        self._config = config
        self._api = api
        self._now = now
        self._sleep = sleep

    def run(self) -> CollectionResult:
        records = 0
        try:
            with Store(
                self._config.state_path,
                max_pending_events=self._config.max_pending_events,
            ) as store:
                emitted = self._emit_pending(store, self._config.max_pending_events)
                for script in self._config.scripts:
                    query_time = self._now()
                    processes = self._fetch_all(store, script, query_time)
                    store.apply_batch(script.alias, processes, query_time)
                    records += len(processes)
                completed_at = self._now()
                store.mark_global_success(completed_at)
                write_metrics(store, self._config.metrics_path, now=completed_at)
                self._emit_pending(
                    store,
                    self._config.max_pending_events - emitted,
                )
                store.prune_terminal_detail(completed_at - self._config.detail_retention)
        except (
            ApiError,
            CollectionBoundExceededError,
            RateLimitedError,
            ResponseTooLargeError,
        ) as error:
            with Store(
                self._config.state_path,
                max_pending_events=self._config.max_pending_events,
            ) as store:
                store.record_failure()
                write_metrics(store, self._config.metrics_path, now=self._now())
            sys.stderr.write(
                json.dumps(
                    {
                        "event": "apps_script.collection_failed",
                        "error": str(error),
                        "error_type": type(error).__name__,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )
            return CollectionResult(success=False, records=0)
        return CollectionResult(success=True, records=records)

    def _fetch_all(
        self, store: Store, script: ScriptConfig, query_time: datetime
    ) -> tuple[Process, ...]:
        retention_cutoff = query_time - self._config.pending_retention
        store.prune_pending(script.alias, retention_cutoff)
        cursor = store.cursor(script.alias)
        started_after = query_time - self._config.initial_lookback
        if cursor is not None:
            started_after = cursor - self._config.overlap
        pending = store.oldest_pending(script.alias)
        if pending is not None and pending < started_after:
            started_after = pending
        token: str | None = None
        processes: list[Process] = []
        for _page_number in range(self._config.max_pages):
            page = self._fetch_with_retry(script, started_after, token)
            processes.extend(page.processes)
            if len(processes) > self._config.max_records:
                bound_name = "records"
                raise CollectionBoundExceededError(bound_name, self._config.max_records)
            token = page.next_page_token
            if token is None:
                return tuple(processes)
        bound_name = "pages"
        raise CollectionBoundExceededError(bound_name, self._config.max_pages)

    def _fetch_with_retry(
        self, script: ScriptConfig, started_after: datetime, token: str | None
    ) -> Page:
        for attempt in range(self._config.max_rate_limit_retries + 1):
            try:
                return self._api.fetch_page(
                    script_id=script.script_id,
                    started_after=started_after,
                    page_token=token,
                    page_size=self._config.page_size,
                )
            except RateLimitedError as error:
                if attempt == self._config.max_rate_limit_retries:
                    raise
                self._sleep(
                    min(error.retry_after_seconds, self._config.max_retry_after.total_seconds())
                )
        raise AssertionError

    @staticmethod
    def _emit_pending(store: Store, limit: int) -> int:
        emitted = 0
        for (
            key,
            alias,
            function,
            process_type,
            status,
            start_time,
            duration,
        ) in store.pending_events(limit):
            sys.stdout.write(
                json.dumps(
                    {
                        "event": "apps_script.execution_terminal",
                        "execution_key": key,
                        "script": alias,
                        "function": function,
                        "type": process_type,
                        "status": status,
                        "start_time": start_time,
                        "duration_seconds": duration,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )
            sys.stdout.flush()
            store.mark_emitted(key)
            emitted += 1
        return emitted


RateLimited = RateLimitedError

__all__ = ["Collector", "Page", "RateLimited"]
