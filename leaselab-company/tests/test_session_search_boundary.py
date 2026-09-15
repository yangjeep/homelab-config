"""Session recall must never select a different company profile database."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "session_guard", Path(__file__).parents[1] / "guard" / "__init__.py"
)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
ROLES = (
    "chief-of-staff",
    "engineer",
    "reviewer",
    "qa-security",
    "sre",
    "support",
    "growth",
)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("target", ROLES)
@pytest.mark.parametrize("embedded", [False, True])
def test_profile_selector_is_bound_to_caller(
    role: str, target: str, embedded: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", role)
    args = (
        {"session_id": f"{target}/synthetic-001"}
        if embedded
        else {"profile": target, "session_id": "synthetic-001"}
    )
    # When
    result = guard.pre_tool_call("session_search", args)
    # Then
    assert (result is None) == (role == target)


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {},
        {"query": "remember"},
        {"session_id": "20260915_001_abc"},
        {"session_id": "synthetic-001", "around_message_id": 1},
    ],
)
def test_current_profile_recall_preserved(
    args: guard.HookValue, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "support")
    # When
    result = guard.pre_tool_call("session_search", args)
    # Then
    assert (result is None) == isinstance(args, dict)


@pytest.mark.parametrize(
    "args",
    [
        {"profile": None},
        {"profile": ""},
        {"profile": " Support "},
        {"profile": "default"},
        {"profile": True},
        {"profile": ["support"]},
        {"session_id": None},
        {"session_id": ""},
        {"session_id": 1},
        {"session_id": {}},
        {"session_id": "support/"},
        {"session_id": "/synthetic"},
        {"session_id": "support/support/synthetic"},
        {"session_id": "../synthetic"},
        {"session_id": "@session:engineer/synthetic"},
        {"session_id": "@session:support/synthetic"},
        {"profile": "support", "session_id": "engineer/synthetic"},
        {"profile": "engineer", "session_id": "support/synthetic"},
        {"profile": None, "session_id": "engineer/synthetic"},
        {"session_id": "support/synthetic\n"},
        {"session_id": "synthetic", "profile_name": "engineer"},
        {"db": "/tmp/state.db"},
    ],
)
def test_malformed_ambiguous_or_conflicting_selectors_denied(
    args: guard.HookValue, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "support")
    # When
    result = guard.pre_tool_call("session_search", args)
    # Then
    assert result is not None and result["action"] == "block"
