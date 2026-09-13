from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class ScriptConfig:
    alias: str
    script_id: str


@dataclass(frozen=True, slots=True)
class CollectorConfig:
    scripts: tuple[ScriptConfig, ...]
    state_path: Path
    metrics_path: Path
    initial_lookback: timedelta
    overlap: timedelta
    page_size: int
    max_pages: int
    max_records: int
    max_rate_limit_retries: int
    max_retry_after: timedelta
    pending_retention: timedelta = timedelta(days=7)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    google_oauth_client_config: Path
    google_oauth_refresh_token_file: Path
    apps_script_scripts: str = Field(min_length=3)
    apps_script_api_url: str = "https://script.googleapis.com/v1/processes:listScriptProcesses"
    apps_script_state_path: Path = Path("/var/lib/apps-script-observer/state.sqlite3")
    apps_script_metrics_path: Path = Path("/var/lib/prometheus/node-exporter/apps_script.prom")

    def collector_config(self) -> CollectorConfig:
        scripts = tuple(_parse_script(item) for item in self.apps_script_scripts.split(","))
        return CollectorConfig(
            scripts=scripts,
            state_path=self.apps_script_state_path,
            metrics_path=self.apps_script_metrics_path,
            initial_lookback=timedelta(days=7),
            overlap=timedelta(minutes=10),
            page_size=50,
            max_pages=20,
            max_records=1_000,
            max_rate_limit_retries=2,
            max_retry_after=timedelta(seconds=10),
            pending_retention=timedelta(days=7),
        )


def _parse_script(raw: str) -> ScriptConfig:
    alias, separator, script_id = raw.strip().partition("=")
    if not separator or not alias or not script_id:
        msg = "APPS_SCRIPT_SCRIPTS entries must use alias=script_id"
        raise ValueError(msg)
    if not alias.replace("-", "").replace("_", "").isalnum():
        msg = "script aliases may contain only letters, numbers, dashes, and underscores"
        raise ValueError(msg)
    return ScriptConfig(alias=alias, script_id=script_id)


def load_runtime_config() -> RuntimeConfig:
    names = RuntimeConfig.model_fields
    values = {name: os.environ[name.upper()] for name in names if name.upper() in os.environ}
    return RuntimeConfig.model_validate(values)
