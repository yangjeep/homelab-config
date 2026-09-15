"""Boundary tests for company telemetry."""
import sqlite3
from pathlib import Path

import company_metrics as metrics
import pytest
from pydantic import ValidationError


def test_task_counts_when_unknown_labels_and_private_content(tmp_path: Path) -> None:
    # Given a real database with approved and untrusted labels and private content.
    path = tmp_path / "kanban.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE tasks (assignee TEXT, status TEXT, body TEXT)")
        db.executemany("INSERT INTO tasks VALUES (?,?,?)", [
            ("support", "done", "PRIVATE_BODY"),
            ("support", "done", "PRIVATE_BODY"),
            ('secret-role"', "PRIVATE_STATUS", "PRIVATE_BODY"),
        ])
    # When aggregating from SQLite.
    output = metrics.kanban_metrics(path)
    # Then only bounded labels and numeric counts leave the boundary.
    assert 'role="support",status="done"} 2' in output
    assert 'role="other",status="other"} 1' in output
    assert "PRIVATE" not in output
    assert "secret-role" not in output


def test_key_metrics_when_response_contains_secret_fields() -> None:
    # Given an API response with numeric usage and unnecessary sensitive metadata.
    payload = '{"data":{"usage":2,"usage_monthly":1,"usage_daily":0.5,"label":"SECRET","is_management_key":false}}'
    # When parsing the allowlisted schema and rendering metrics.
    key = metrics.KeyEnvelope.model_validate_json(payload)
    output = metrics.key_metrics(key.data, "support")
    # Then only approved numeric fields survive.
    assert 'period="monthly"} 1.0' in output
    assert "SECRET" not in output


def test_key_schema_when_nonfinite_usage() -> None:
    # Given invalid provider numeric data.
    payload = '{"data":{"usage":NaN,"usage_monthly":1,"usage_daily":0,"is_management_key":false}}'
    # When parsing the response, then fail closed.
    with pytest.raises(ValidationError):
        metrics.KeyEnvelope.model_validate_json(payload)


def test_readonly_database_when_missing(tmp_path: Path) -> None:
    # Given a nonexistent board database.
    path = tmp_path / "absent.db"
    # When collecting, then no empty replacement database is created.
    with pytest.raises(sqlite3.OperationalError):
        metrics.kanban_metrics(path)
    assert not path.exists()


def test_key_schema_when_management_credential() -> None:
    # Given an accidental management credential response.
    payload = '{"data":{"usage":0,"usage_monthly":0,"usage_daily":0,"is_management_key":true}}'
    # When parsing, then reject rather than exposing management usage.
    with pytest.raises(ValidationError):
        metrics.KeyEnvelope.model_validate_json(payload)


def test_fetch_when_http_error_hides_response(tmp_path: Path) -> None:
    import httpx
    # Given a credential file and a provider error containing sensitive content.
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=TEST_CREDENTIAL\n")

    def endpoint(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer TEST_CREDENTIAL"
        return httpx.Response(401, json={"error": "SECRET_RESPONSE"})

    # When fetching via the HTTP adapter, then fail with an HTTP status error.
    with httpx.Client(transport=httpx.MockTransport(endpoint)) as client, pytest.raises(httpx.HTTPStatusError):
        metrics.fetch_key(client, tmp_path)


def test_main_when_source_fails_retains_last_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # Given a successful previous sample but missing current profile credentials/database.
    state = tmp_path / "state.json"
    state.write_text('{"sources":{"support":{"last_success":123,"failures":2}}}')
    output = tmp_path / "metrics.prom"
    monkeypatch.setattr(metrics, "ROOT", tmp_path)
    monkeypatch.setattr(metrics, "STATE", state)
    monkeypatch.setattr(metrics, "OUTPUT", output)
    # When running one failed collection, then keep freshness and increment failures.
    assert metrics.main() == 1
    text = output.read_text()
    assert 'source="support"} 123.0' in text
    assert 'leaselab_company_source_failures_total{source="support"} 3' in text
    assert 'leaselab_company_source_success{source="support"} 0' in text
    assert "leaselab_openrouter_usage_usd" not in text
    assert "Traceback" not in capsys.readouterr().err
