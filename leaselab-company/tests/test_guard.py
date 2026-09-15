"""Standalone permission policy tests; no Hermes installation required."""

import importlib.util
from collections.abc import Callable, MutableMapping
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "company_guard", Path(__file__).parents[1] / "guard" / "__init__.py"
)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def test_denies_callback_when_profile_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    # When
    directive = guard.pre_tool_call("memory")
    # Then
    assert directive is not None and directive["action"] == "block"


@pytest.mark.parametrize("role", ["", "unknown", "cos", "COS", "../engineer"])
def test_denies_when_identity_is_not_exact(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", role)
    # When
    directive = guard.pre_tool_call("kanban_show", profile="engineer")
    # Then
    assert directive["action"] == "block"


@pytest.mark.parametrize(
    "role",
    [
        "chief-of-staff",
        "support",
        "sre",
        "engineer",
        "reviewer",
        "qa-security",
        "growth",
    ],
)
@pytest.mark.parametrize(
    "name",
    [
        "execute_code",
        "delegate_task",
        "process",
        "browser_navigate",
        "web_search",
        "tools_config",
        "plugin_install",
        "mcp__company__execute",
        "mcp__other__memory",
        "terminal ",
        "read_file ",
    ],
)
def test_denies_bridges_and_unknown_tools(
    role: str, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", role)
    # When
    directive = guard.pre_tool_call(name)
    # Then
    assert directive["action"] == "block"


@pytest.mark.parametrize(
    "name",
    [
        "memory",
        "skills_list",
        "skill_view",
        "skill_manage",
        "session_search",
        "kanban_list",
        "kanban_create",
        "kanban_link",
        "kanban_unblock",
        "company_github",
    ],
)
def test_allows_chief_of_staff_native_tools(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    # When
    directive = guard.pre_tool_call(
        name, args={"assignee": "engineer"} if name == "kanban_create" else {}
    )
    # Then
    assert directive is None


@pytest.mark.parametrize(
    "role", ["support", "sre", "engineer", "reviewer", "qa-security", "growth", ""]
)
def test_denies_company_github_for_non_cos(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", role)
    # When
    directive = guard.pre_tool_call("company_github", args={"action": "repo_read"})
    # Then
    assert directive is not None and directive["action"] == "block"


@pytest.mark.parametrize(
    "role",
    ["support", "sre", "engineer", "reviewer", "qa-security", "growth", "default"],
)
def test_denies_task_creation_when_caller_is_not_chief_of_staff(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", role)
    # When
    directive = guard.pre_tool_call("kanban_create", args={"assignee": "engineer"})
    # Then
    assert directive["action"] == "block"


@pytest.mark.parametrize(
    "assignee",
    [
        "chief-of-staff",
        "support",
        "sre",
        "engineer",
        "reviewer",
        "qa-security",
        "growth",
    ],
)
def test_allows_task_creation_when_assignee_is_exact_company_profile(
    assignee: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    # When
    directive = guard.pre_tool_call("kanban_create", args={"assignee": assignee})
    # Then
    assert directive is None


@pytest.mark.parametrize(
    "args",
    [
        None,
        "engineer",
        [],
        {},
        {"profile": "engineer"},
        {"assignee": None},
        {"assignee": "default"},
        {"assignee": "unknown"},
        {"assignee": ""},
        {"assignee": "Engineer"},
        {"assignee": " engineer"},
        {"assignee": "engineer "},
        {"assignee": "../engineer"},
        {"assignee": ["engineer"]},
        {"assignee": {}},
        {"assignee": 1},
        {"assignee": True},
    ],
)
def test_denies_task_creation_when_native_arguments_are_invalid(
    args: str
    | list[str]
    | dict[str, str | int | list[str] | dict[str, str] | None]
    | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    # When
    directive = guard.pre_tool_call("kanban_create", args=args, assignee="engineer")
    # Then
    assert directive["action"] == "block"


def test_denies_task_creation_when_native_arguments_are_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    # When
    directive = guard.pre_tool_call("kanban_create", assignee="engineer")
    # Then
    assert directive["action"] == "block"


@pytest.mark.parametrize(
    "name", ["terminal", "read_file", "write_file", "patch", "search_files"]
)
def test_denies_chief_of_staff_execution(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "chief-of-staff")
    # When
    directive = guard.pre_tool_call(name)
    # Then
    assert directive["action"] == "block"


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> MutableMapping[str, str | int]:
    config: MutableMapping[str, str | int] = {
        "env_type": "ssh",
        "ssh_host": "127.0.0.1",
        "ssh_port": 22,
        "ssh_user": "leaselab-engineer",
        "ssh_key": "/etc/leaselab-company/ssh/engineer",
    }
    monkeypatch.setenv("HERMES_PROFILE", "engineer")
    monkeypatch.setattr(guard, "_terminal_config", lambda: config)
    return config


@pytest.mark.parametrize(
    "name", ["terminal", "read_file", "write_file", "patch", "search_files"]
)
@pytest.mark.parametrize(
    "role", ["support", "sre", "engineer", "reviewer", "qa-security", "growth"]
)
def test_allows_specialist_execution_when_ssh_identity_matches(
    name: str,
    role: str,
    backend: MutableMapping[str, str | int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", role)
    backend.update(
        ssh_user=f"leaselab-{role}", ssh_key=f"/etc/leaselab-company/ssh/{role}"
    )
    # When
    directive = guard.pre_tool_call(name)
    # Then
    assert directive is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("env_type", "local"),
        ("env_type", "docker"),
        ("ssh_host", "remote.invalid"),
        ("ssh_user", "hermes"),
        ("ssh_user", "leaselab-sre"),
        ("ssh_port", "22"),
        ("ssh_port", 2222),
        ("ssh_key", "/etc/leaselab-company/ssh/sre"),
    ],
)
@pytest.mark.parametrize(
    "name", ["terminal", "read_file", "write_file", "patch", "search_files"]
)
def test_denies_execution_when_effective_backend_mismatches(
    key: str,
    value: str | int,
    name: str,
    backend: MutableMapping[str, str | int],
) -> None:
    # Given
    backend[key] = value
    # When
    directive = guard.pre_tool_call(name)
    # Then
    assert directive["action"] == "block"


@pytest.mark.parametrize(
    "key", ["env_type", "ssh_host", "ssh_user", "ssh_port", "ssh_key"]
)
def test_denies_execution_when_backend_field_missing(
    key: str, backend: MutableMapping[str, str | int]
) -> None:
    # Given
    del backend[key]
    # When
    directive = guard.pre_tool_call("terminal")
    # Then
    assert directive["action"] == "block"


@pytest.mark.parametrize("name", ["kanban_list", "kanban_unblock"])
def test_denies_worker_orchestrator_tool(
    name: str, backend: MutableMapping[str, str | int]
) -> None:
    # Given
    assert backend["ssh_user"] == "leaselab-engineer"
    # When
    directive = guard.pre_tool_call(name)
    # Then
    assert directive["action"] == "block"


def test_denies_when_native_resolver_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    def unavailable() -> None:
        raise RuntimeError

    monkeypatch.setenv("HERMES_PROFILE", "engineer")
    monkeypatch.setattr(guard, "_terminal_config", unavailable)
    # When
    directive = guard.pre_tool_call("terminal")
    # Then
    assert directive["action"] == "block"


def test_registers_native_callback() -> None:
    # Given
    callbacks: dict[str, Callable[..., None]] = {}
    registrations: list[dict[str, guard.HookValue]] = []

    class Context:
        def register_hook(self, name: str, callback: Callable[..., None]) -> None:
            callbacks[name] = callback

        def register_tool(self, **kwargs: guard.HookValue) -> None:
            registrations.append(kwargs)

    # When
    guard.register(Context())
    # Then
    assert callbacks["pre_tool_call"] is guard.pre_tool_call
    assert registrations[0]["name"] == "send_message"
    assert registrations[0]["toolset"] == "leaselab-slack-send"
    assert registrations[0]["handler"] is guard._send_slack_native


@pytest.mark.parametrize(
    "role,channel,prefix",
    [
        ("chief-of-staff", "C0C2Q3Y1QF2", "Chief of Staff"),
        ("engineer", "C0C2Q43J0KS", "Engineer"),
        ("reviewer", "C0C1XMT2BU1", "Reviewer"),
        ("qa-security", "C0C1PH369DH", "QA/Security"),
        ("support", "C0C1XMYQMR7", "Support"),
        ("sre", "C0C1XMYQMR7", "SRE"),
        ("growth", "C0C1R45U8SH", "Growth"),
    ],
)
@pytest.mark.parametrize("thread", ["", ":1790000000.000001"])
def test_allows_slack_role_route(
    role: str, channel: str, prefix: str, thread: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", role)
    # When
    result = guard.pre_tool_call(
        "send_message",
        args={
            "action": "send",
            "target": f"slack:{channel}{thread}",
            "message": f"[{prefix}] Evidence ready.",
        },
    )
    # Then
    assert result is None


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {},
        {"action": "list"},
        {"target": "telegram:660328434", "message": "[Engineer] Hi"},
        {"target": "slack:C0C2Q3Y1QF2", "message": "[Engineer] Hi"},
        {"target": "slack:C0C2Q43J0KS", "message": "   "},
        {"target": "slack:C0C2Q43J0KS", "message": "[Engineer] MEDIA:/etc/passwd"},
        {
            "target": "slack:C0C2Q43J0KS",
            "message": "[Engineer] Hi",
            "thread_id": "1790000000.000001",
        },
        {"target": "slack:C0C2Q43J0KS", "message": "[Engineer] Hi", "action": "react"},
        {"target": ["slack:C0C2Q43J0KS"], "message": "[Engineer] Hi"},
        {"target": "slack:C0C2Q43J0KS", "message": 1},
    ],
)
def test_denies_slack_invalid_request(
    args: guard.HookValue, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "engineer")
    # When
    result = guard.pre_tool_call("send_message", args=args)
    # Then
    assert result is not None and result["action"] == "block"


@pytest.mark.parametrize(
    "target",
    [
        "slack",
        "slack:#engineering",
        "slack:U0225R7NP8Q",
        "slack:D0C2Q43J0KS",
        "slack:C0C2Q43J0KS:bad",
        "slack:C0C2Q43J0KS:1790000000",
        "slack:C0C2Q43J0KS:1790000000.000001:extra",
        " slack:C0C2Q43J0KS",
        "slack:C0C2Q43J0KS\n",
        "slack:C0C2Q43J0KS:١٧٩٠٠٠٠٠٠٠.٠٠٠٠٠١",
        "slack:C0C2Q43J0KS:1790000000.000001\n",
        "slack:C9999999999",
    ],
)
def test_denies_slack_ambiguous_target(
    target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "engineer")
    # When
    result = guard.pre_tool_call(
        "send_message", args={"target": target, "message": "[Engineer] Hi"}
    )
    # Then
    assert result is not None and result["action"] == "block"


def test_registered_sender_denies_without_loading_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", "support")
    # When
    result = guard._send_slack_native(
        {"target": "telegram:660328434", "message": "[Support] Hi"}
    )
    # Then
    assert '"error"' in result


@pytest.mark.parametrize(
    "role,prefix,allowed",
    [
        ("chief-of-staff", "Chief of Staff", {0, 1, 2, 3, 4, 5}),
        ("engineer", "Engineer", {1, 2, 4, 5}),
        ("reviewer", "Reviewer", {1, 2}),
        ("qa-security", "QA/Security", {1, 2, 3}),
        ("sre", "SRE", {3, 4}),
        ("support", "Support", {3, 4}),
        ("growth", "Growth", {5}),
    ],
)
@pytest.mark.parametrize(
    "index,channel",
    list(
        enumerate(
            [
                "C0C2Q3Y1QF2",
                "C0C2Q43J0KS",
                "C0C1XMT2BU1",
                "C0C1PH369DH",
                "C0C1XMYQMR7",
                "C0C1R45U8SH",
            ]
        )
    ),
)
def test_slack_channel_membership_matrix(
    role: str,
    prefix: str,
    allowed: set[int],
    index: int,
    channel: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("HERMES_PROFILE", role)
    # When
    result = guard.pre_tool_call(
        "send_message",
        args={"target": f"slack:{channel}", "message": f"[{prefix}] Evidence"},
    )
    # Then
    assert (result is None) == (index in allowed)


def test_distinct_slack_identity_does_not_require_display_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_PROFILE", "engineer")
    assert (
        guard.pre_tool_call(
            "send_message",
            args={"target": "slack:C0C2Q43J0KS", "message": "Evidence ready."},
        )
        is None
    )


def test_incident_destination_requires_root_managed_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    import os

    path = tmp_path / "identities.json"
    path.write_text(
        json.dumps(
            {
                "team_id": "T021CUR5KTP",
                "founder_user_id": "U0225R7NP8Q",
                "channels": ["CINCIDENTS"],
                "incident_channel_id": "CINCIDENTS",
            }
        )
    )
    path.chmod(0o644)
    monkeypatch.setattr(guard, "SLACK_IDENTITIES", path)
    assert guard._incident_channel_allowed("CINCIDENTS") is (os.getuid() == 0)
    path.chmod(0o666)
    assert guard._incident_channel_allowed("CINCIDENTS") is False


def test_incident_mapping_symlink_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real.json"
    real.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    monkeypatch.setattr(guard, "SLACK_IDENTITIES", link)
    assert guard._incident_channel_allowed("CINCIDENTS") is False


@pytest.mark.parametrize("role", tuple(guard.ROLE_TOOLS))
def test_management_tools_preserve_single_dispatcher(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_PROFILE", role)
    assert (
        guard.pre_tool_call("company_management", args={"action": "weekly_start"})
        is None
    ) is (role == "chief-of-staff")
    assert (
        guard.pre_tool_call(
            "company_request_coordination",
            args={"intent": "synthetic", "source_ref": "slack:test"},
        )
        is None
    ) is (role != "chief-of-staff")
