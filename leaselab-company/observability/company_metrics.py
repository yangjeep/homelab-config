#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx==0.28.1", "pydantic==2.13.4", "python-dotenv==1.2.2"]
# ///
# Run: existing Hermes venv/bin/python company_metrics.py (installed systemd unit).
"""Publish bounded company aggregates; never publish task bodies or API metadata."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import ClassVar, Final, Literal

import httpx
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

ROOT: Final = Path("/var/lib/leaselab-company")
STATE: Final = Path("/var/lib/leaselab-company-metrics/state.json")
OUTPUT: Final = Path("/var/lib/prometheus/node-exporter/leaselab-company.prom")
ROLES: Final = ("chief-of-staff", "support", "sre", "engineer", "reviewer", "qa-security", "growth")
STATUSES: Final = ("triage", "todo", "scheduled", "ready", "running", "blocked", "review", "done", "archived")
ENDPOINT: Final = "https://openrouter.ai/api/v1/key"


class KeyData(BaseModel):
    """Only numeric usage crosses the provider boundary; metadata is discarded."""
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, allow_inf_nan=False)
    usage: float = Field(ge=0)
    usage_monthly: float = Field(ge=0)
    usage_daily: float = Field(ge=0)
    is_management_key: Literal[False]


class KeyEnvelope(BaseModel):
    """Official current-key response."""
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    data: KeyData


class SampleState(BaseModel):
    """Persistent collection health, containing no provider response or credentials."""
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, allow_inf_nan=False)
    last_success: float = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)


class CollectorState(BaseModel):
    """Fixed sources retain failure counters between timer invocations."""
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
    sources: dict[str, SampleState] = Field(default_factory=dict)


class CredentialError(RuntimeError):
    """Profile credential missing or response exceeds the permitted size."""


def kanban_metrics(path: Path) -> str:
    """Read only aggregate counts from the named board using bounded labels."""
    with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=3)) as db:
        _ = db.execute("PRAGMA query_only=ON")
        rows = TypeAdapter(list[tuple[str | None, str, int]]).validate_python(
            db.execute("SELECT assignee,status,count(*) FROM tasks GROUP BY assignee,status").fetchall(),
        )
    counts: Counter[tuple[str, str]] = Counter()
    for assignee, status, count in rows:
        role_label = assignee if assignee in ROLES else "other"
        status_label = status if status in STATUSES else "other"
        counts[(role_label, status_label)] += count
    return "".join(
        f'leaselab_kanban_tasks{{role="{role}",status="{status}"}} {counts[(role, status)]}\n'
        for role in (*ROLES, "other") for status in (*STATUSES, "other")
    )


def key_metrics(data: KeyData, role: str) -> str:
    """Render only fixed period labels and numeric currency values."""
    return "".join(
        f'leaselab_openrouter_usage_usd{{role="{role}",period="{period}"}} {value}\n'
        for period, value in (("lifetime", data.usage), ("monthly", data.usage_monthly), ("daily", data.usage_daily))
    )


def fetch_key(client: httpx.Client, profile: Path) -> KeyData:
    """Use the role key in memory; disable env interpolation and HTTP redirects."""
    key = dotenv_values(profile / ".env", interpolate=False).get("OPENROUTER_API_KEY")
    if not key:
        raise CredentialError
    with client.stream("GET", ENDPOINT, headers={"Authorization": f"Bearer {key}"}) as response:
        _ = response.raise_for_status()
        payload = bytearray()
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > 65536:
                raise CredentialError
    return KeyEnvelope.model_validate_json(payload).data


def atomic_write(path: Path, content: str, mode: int) -> None:
    """Publish complete files on the same filesystem, with restrictive permissions."""
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            _ = handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), mode)
            _ = os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def main() -> int:
    """Collect sources independently; health metrics explain omitted stale values."""
    previous = CollectorState.model_validate_json(STATE.read_text()) if STATE.exists() else CollectorState()
    sources = dict(previous.sources)
    lines = [f"leaselab_company_metrics_attempt_seconds {time.time()}\n"]
    failures = 0
    with httpx.Client(timeout=httpx.Timeout(10, connect=5), follow_redirects=False, trust_env=False) as client:
        for source in ("kanban", *ROLES):
            old = previous.sources.get(source, SampleState())
            success = False
            try:
                value = (
                    kanban_metrics(ROOT / "kanban/boards/leaselab-company/kanban.db")
                    if source == "kanban"
                    else key_metrics(fetch_key(client, ROOT / "profiles" / source), source)
                )
                lines.append(value)
                success = True
                sources[source] = SampleState(last_success=time.time(), failures=old.failures)
            except (OSError, sqlite3.Error, httpx.HTTPError, ValidationError, CredentialError):
                failures += 1
                sources[source] = SampleState(last_success=old.last_success, failures=old.failures + 1)
                print(f"company_metrics_source_failed source={source}", file=sys.stderr)
            current = sources[source]
            lines.extend((
                f'leaselab_company_source_success{{source="{source}"}} {int(success)}\n',
                f'leaselab_company_source_last_success_seconds{{source="{source}"}} {current.last_success}\n',
                f'leaselab_company_source_failures_total{{source="{source}"}} {current.failures}\n',
            ))
    lines.append(f"leaselab_company_metrics_completed_seconds {time.time()}\n")
    atomic_write(STATE, CollectorState(sources=sources).model_dump_json(), 0o600)
    atomic_write(OUTPUT, "".join(lines), 0o644)
    print(f"company_metrics_completed failed_sources={failures}")
    return int(failures > 0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValidationError):
        print("company_metrics_state_or_publish_failed", file=sys.stderr)
        sys.exit(1)
