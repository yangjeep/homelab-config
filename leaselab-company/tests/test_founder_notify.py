"""Founder notifications have one identity, one destination, and text-only input."""

import importlib.util
import sys
import types
from collections.abc import Callable, Mapping
from pathlib import Path

HookValue = str | int | float | bool | None | list["HookValue"] | dict[str, "HookValue"]

import pytest

SPEC = importlib.util.spec_from_file_location(
    "founder_guard", Path(__file__).parents[1] / "guard" / "__init__.py"
)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
MESSAGE = "[Chief of Staff] Founder decision required."


@pytest.mark.parametrize(
    "role",
    ["", "unknown", "support", "sre", "engineer", "reviewer", "qa-security", "growth"],
)
def test_non_cos_denied(role: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", role)
    assert (
        guard.pre_tool_call("company_founder_notify", {"message": MESSAGE})["action"]
        == "block"
    )
    assert "error" in guard._notify_founder_native({"message": MESSAGE})


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        "text",
        {},
        {"message": None},
        {"message": []},
        {"message": "hello"},
        {"message": "[Chief of Staff] "},
        {"message": MESSAGE, "target": "telegram:1"},
        {"message": MESSAGE, "action": "send"},
        {"message": MESSAGE, "thread_id": "1"},
        {"message": MESSAGE + "x" * 3000},
        *[
            {"message": MESSAGE + marker}
            for marker in (
                "MEDIA:/tmp/test",
                "media:/tmp/test.png",
                "MeDiA:/tmp/test.png",
                "mEdİa:/tmp/test.png",
                "[[as_document]]",
                "[[audio_as_voice]]",
                "\x00",
            )
        ],
    ],
)
def test_bad_input_denied(args: HookValue, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    assert guard.pre_tool_call("company_founder_notify", args)["action"] == "block"
    assert "error" in guard._notify_founder_native(args)


def test_cos_native_fixed_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    calls: list[dict[str, HookValue]] = []
    native = types.ModuleType("tools.send_message_tool")

    def capture(args: dict[str, HookValue]) -> str:
        calls.append(args)
        return '{"success":true}'

    monkeypatch.setattr(native, "send_message_tool", capture, raising=False)
    monkeypatch.setitem(sys.modules, "tools.send_message_tool", native)
    assert guard.pre_tool_call("company_founder_notify", {"message": MESSAGE}) is None
    assert guard._notify_founder_native({"message": MESSAGE}) == '{"success":true}'
    assert calls == [
        {"action": "send", "target": "telegram:660328434", "message": MESSAGE}
    ]


@pytest.mark.parametrize(
    "role",
    [
        "chief-of-staff",
        "support",
        "engineer",
        "reviewer",
        "qa-security",
        "sre",
        "growth",
        "",
    ],
)
def test_only_cos_registration(role: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_PROFILE", role)
    calls: list[tuple[str, Mapping[str, HookValue]]] = []

    class Context:
        def register_hook(
            self, hook_name: str, callback: Callable[..., object]
        ) -> None:
            assert hook_name == "pre_tool_call"
            assert callable(callback)

        def register_tool(
            self,
            *,
            name: str,
            toolset: str,
            schema: Mapping[str, HookValue],
            handler: Callable[..., str],
        ) -> None:
            assert toolset == "leaselab-slack-send"
            assert callable(handler)
            calls.append((name, schema))

    guard.register(Context())
    found = [schema for name, schema in calls if name == "company_founder_notify"]
    assert bool(found) == (role == "chief-of-staff")
    if found:
        parameters = found[0]["parameters"]
        assert isinstance(parameters, dict)
        assert parameters["additionalProperties"] is False
        properties = parameters["properties"]
        assert isinstance(properties, dict)
        assert set(properties) == {"message"}


@pytest.mark.parametrize("marker", ["MEDIA:", "media:", "MeDiA:", "mEdİa:"])
def test_slack_native_media_case_denied(
    marker: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    args = {
        "target": "slack:C0C2Q3Y1QF2",
        "message": "[Chief of Staff] " + marker + "/tmp/canary.png",
    }
    assert guard.pre_tool_call("send_message", args)["action"] == "block"
    assert "error" in guard._send_slack_native(args)
