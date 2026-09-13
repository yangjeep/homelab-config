from __future__ import annotations

import os
import tempfile
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .store import Store

_ALLOWED_TYPES = frozenset(
    {"ADD_ON", "EXECUTION_API", "TIME_DRIVEN", "TRIGGER", "WEBAPP", "EDITOR"}
)
_ALLOWED_STATUSES = frozenset({"COMPLETED", "CANCELED", "FAILED", "TIMED_OUT"})
_DURATION_BUCKETS = (0.1, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 900.0, 3600.0)


def write_metrics(store: Store, path: Path, *, now: datetime | None = None) -> None:
    metric_time = now or datetime.now(tz=UTC)
    failures, last_success = store.metric_state()
    lines = [
        "# HELP homelab_apps_script_collector_failures_total Failed collection runs.",
        "# TYPE homelab_apps_script_collector_failures_total counter",
        f"homelab_apps_script_collector_failures_total {failures}",
        (
            "# HELP homelab_apps_script_collector_last_success_timestamp_seconds "
            "Last successful collection."
        ),
        "# TYPE homelab_apps_script_collector_last_success_timestamp_seconds gauge",
        f"homelab_apps_script_collector_last_success_timestamp_seconds {last_success:.3f}",
        "# HELP homelab_apps_script_executions_terminal_total Terminal executions observed.",
        "# TYPE homelab_apps_script_executions_terminal_total counter",
    ]
    observations: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for alias, process_type, status, duration in store.terminal_observations():
        safe_type = process_type if process_type in _ALLOWED_TYPES else "OTHER"
        safe_status = status if status in _ALLOWED_STATUSES else "OTHER"
        key = (alias, safe_type, safe_status)
        counts[key] += 1
        if duration is not None:
            observations[key].append(duration)
    for (alias, safe_type, safe_status), count in sorted(counts.items()):
        lines.append(
            "homelab_apps_script_executions_terminal_total"
            f'{{script="{alias}",type="{safe_type}",status="{safe_status}"}} {count}'
        )
    _append_recent_metrics(lines, store, metric_time)
    lines.extend(
        [
            "# HELP homelab_apps_script_execution_duration_seconds Terminal execution duration.",
            "# TYPE homelab_apps_script_execution_duration_seconds histogram",
        ]
    )
    for (alias, safe_type, safe_status), durations in sorted(observations.items()):
        labels = f'script="{alias}",type="{safe_type}",status="{safe_status}"'
        for bucket in _DURATION_BUCKETS:
            cumulative = sum(duration <= bucket for duration in durations)
            lines.append(
                "homelab_apps_script_execution_duration_seconds_bucket"
                f'{{{labels},le="{bucket:g}"}} {cumulative}'
            )
        lines.append(
            "homelab_apps_script_execution_duration_seconds_bucket"
            f'{{{labels},le="+Inf"}} {len(durations)}'
        )
        lines.append(
            f"homelab_apps_script_execution_duration_seconds_sum{{{labels}}} {sum(durations):.6f}"
        )
        lines.append(
            f"homelab_apps_script_execution_duration_seconds_count{{{labels}}} {len(durations)}"
        )
    lines.extend(
        [
            (
                "# HELP homelab_apps_script_last_success_timestamp_seconds "
                "Last successful execution."
            ),
            "# TYPE homelab_apps_script_last_success_timestamp_seconds gauge",
        ]
    )
    for alias, timestamp in sorted(store.successful_execution_times().items()):
        lines.append(
            "homelab_apps_script_last_success_timestamp_seconds"
            f'{{script="{alias}"}} {timestamp:.3f}'
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o644)
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _append_recent_metrics(lines: list[str], store: Store, metric_time: datetime) -> None:
    recent_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    recent_max_duration: dict[str, float] = {}
    for alias, process_type, status, duration in store.terminal_observations_since(
        metric_time - timedelta(hours=24)
    ):
        safe_type = process_type if process_type in _ALLOWED_TYPES else "OTHER"
        safe_status = status if status in _ALLOWED_STATUSES else "OTHER"
        recent_counts[(alias, safe_type, safe_status)] += 1
        if duration is not None:
            recent_max_duration[alias] = max(duration, recent_max_duration.get(alias, duration))
    lines.extend(
        [
            (
                "# HELP homelab_apps_script_executions_last_24h "
                "Terminal executions started in the last 24 hours."
            ),
            "# TYPE homelab_apps_script_executions_last_24h gauge",
        ]
    )
    for (alias, safe_type, safe_status), count in sorted(recent_counts.items()):
        lines.append(
            "homelab_apps_script_executions_last_24h"
            f'{{script="{alias}",type="{safe_type}",status="{safe_status}"}} {count}'
        )
    lines.extend(
        [
            (
                "# HELP homelab_apps_script_max_duration_seconds_last_24h "
                "Longest execution started in the last 24 hours."
            ),
            "# TYPE homelab_apps_script_max_duration_seconds_last_24h gauge",
        ]
    )
    for alias, duration in sorted(recent_max_duration.items()):
        lines.append(
            f'homelab_apps_script_max_duration_seconds_last_24h{{script="{alias}"}} {duration:.6f}'
        )
