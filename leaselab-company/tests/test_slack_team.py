"""Exercise real Bolt dispatch, not a hand-called middleware predicate."""
import importlib.util
from importlib import import_module
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
from pydantic import JsonValue
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.authorization import AuthorizeResult
from slack_bolt.request.async_request import AsyncBoltRequest

PACKAGE = Path(__file__).parents[1] / "slack-team"
SPEC = importlib.util.spec_from_file_location("company_slack_team", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)])
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
POLICY = import_module("company_slack_team.policy")
COS, FOUNDER, TEAM, ROLES = POLICY.COS, POLICY.FOUNDER, POLICY.TEAM, POLICY.ROLES
Identities = POLICY.Identities

MAP = Identities.model_validate({
    "team_id": TEAM, "founder_user_id": FOUNDER,
    "channels": ["C001", "C002"], "incident_channel_id": "C002",
    "roles": {role: {"app_id": f"A{index}", "bot_user_id": f"U{index}"} for index, role in enumerate(sorted(ROLES), 1)},
})


def payload(role: str, text: str) -> dict[str, JsonValue]:
    return {"type": "event_callback", "team_id": TEAM, "api_app_id": MAP.roles[role].app_id,
            "event_id": "Ev001", "event": {"type": "message", "user": FOUNDER, "text": text,
            "channel": "C001", "channel_type": "channel", "ts": "100.001", "client_msg_id": "msg1"}}


async def dispatch(body: dict[str, JsonValue], role: str, verified: str | None = None) -> tuple[int, list[dict[str, JsonValue]]]:
    received: list[dict[str, JsonValue]] = []
    identity = MAP.roles[role]

    async def authorize() -> AuthorizeResult:
        return AuthorizeResult(enterprise_id=None, team_id=TEAM, bot_user_id=identity.bot_user_id, bot_token="xoxb-test")

    app = AsyncApp(authorize=authorize, request_verification_enabled=False, process_before_response=True)
    adapter = SimpleNamespace(_team_bot_user_ids={TEAM: verified or identity.bot_user_id})
    previous = os.environ.get("HERMES_PROFILE")
    os.environ["HERMES_PROFILE"] = role
    try:
        MODULE.install(app, adapter, MAP)
    finally:
        if previous is None:
            os.environ.pop("HERMES_PROFILE")
        else:
            os.environ["HERMES_PROFILE"] = previous

    @app.event("message")
    @app.event("app_mention")
    async def receive(event: dict[str, JsonValue]) -> None:
        received.append(event.copy())

    response = await app.async_dispatch(AsyncBoltRequest(body=body, mode="socket_mode"))
    return response.status, received


@pytest.mark.parametrize("role", sorted(ROLES))
def test_actual_bolt_direct_role(role: str) -> None:
    status, received = anyio.run(dispatch, payload(role, f"<@{MAP.roles[role].bot_user_id}> status"), role)
    assert status == 200 and len(received) == 1


@pytest.mark.parametrize("role", sorted(ROLES))
def test_actual_bolt_multi_role_only_cos(role: str) -> None:
    text = f"<@{MAP.roles['engineer'].bot_user_id}> <@{MAP.roles['sre'].bot_user_id}> investigate"
    status, received = anyio.run(dispatch, payload(role, text), role)
    assert status == 200
    assert len(received) == (1 if role == COS else 0)
    if received:
        assert received[0]["text"] == f"<@{MAP.roles[COS].bot_user_id}> {text}"
        assert received[0]["_leaselab_original_text"] == text


@pytest.mark.parametrize("field,value", [("team_id", "TOTHER"), ("api_app_id", "AOTHER"), ("type", "other")])
def test_envelope_boundary(field: str, value: str) -> None:
    body = payload("engineer", f"<@{MAP.roles['engineer'].bot_user_id}> fix")
    body[field] = value
    assert anyio.run(dispatch, body, "engineer")[1] == []


@pytest.mark.parametrize("field,value", [("user", "UOTHER"), ("channel", "COTHER"), ("team", "TOTHER"),
    ("subtype", "message_changed"), ("bot_id", "B001"), ("channel_type", "im"), ("text", "<@UUNKNOWN> fix"), ("ts", "bad")])
def test_event_boundary(field: str, value: str) -> None:
    body = payload("engineer", f"<@{MAP.roles['engineer'].bot_user_id}> fix")
    event = body["event"]
    assert isinstance(event, dict)
    event[field] = value
    assert anyio.run(dispatch, body, "engineer")[1] == []


def test_auth_test_must_match_current_role_not_any_role() -> None:
    body = payload("engineer", f"<@{MAP.roles['engineer'].bot_user_id}> fix")
    assert anyio.run(dispatch, body, "engineer", MAP.roles['sre'].bot_user_id)[1] == []


def test_non_message_event_acknowledged_without_llm() -> None:
    body = payload("engineer", "")
    body["event"] = {"type": "reaction_added"}
    assert anyio.run(dispatch, body, "engineer") == (200, [])


@pytest.mark.skipif(not os.environ.get("HERMES_SOURCE_PATH"), reason="requires installed Hermes runtime")
def test_installed_native_prefilter_strict_gate_and_duplicate(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.path.insert(0, os.environ["HERMES_SOURCE_PATH"])
    PlatformConfig = import_module("gateway.config").PlatformConfig
    SlackAdapter = import_module("plugins.platforms.slack.adapter").SlackAdapter

    async def scenario() -> None:
        role = COS
        identity = MAP.roles[role]
        adapter = SlackAdapter(PlatformConfig(enabled=True, extra={"strict_mention": True,
            "require_mention": True, "thread_require_mention": True,
            "allowed_channels": list(MAP.channels), "allow_bots": "none"}))
        adapter._team_bot_user_ids[TEAM] = identity.bot_user_id
        adapter._bot_user_id = identity.bot_user_id
        accepted_messages = []

        async def authorize() -> AuthorizeResult:
            return AuthorizeResult(enterprise_id=None, team_id=TEAM, bot_user_id=identity.bot_user_id, bot_token="xoxb-test")

        app = AsyncApp(authorize=authorize, request_verification_enabled=False, process_before_response=True)
        monkeypatch.setenv("HERMES_PROFILE", role)
        MODULE.install(app, adapter, MAP)

        @app.event("message")
        @app.event("app_mention")
        async def receive(event: dict[str, JsonValue], body: dict[str, JsonValue]) -> None:
            accepted = await adapter._prefilter_inbound(event, body)
            if accepted is None:
                return
            normalized, team, channel = accepted
            text = normalized["text"]
            mentioned = f"<@{identity.bot_user_id}>" in text
            gate = await adapter._channel_gate_allows(channel_id=channel, routing_text=text,
                bot_uid=identity.bot_user_id, is_mentioned=mentioned, is_thread_reply=False,
                event_thread_ts=None, user_id=FOUNDER, team_id=team, is_dm=False, force_process=False)
            if gate:
                accepted_messages.append(normalized)

        text = f"<@{MAP.roles['engineer'].bot_user_id}> <@{MAP.roles['sre'].bot_user_id}> synthetic"
        first = payload(role, text)
        second = payload(role, text)
        second_event = second["event"]
        assert isinstance(second_event, dict)
        second_event["type"] = "app_mention"
        for body in (first, second):
            response = await app.async_dispatch(AsyncBoltRequest(body=body, mode="socket_mode"))
            assert response.status == 200
        assert len(accepted_messages) == 1
        assert accepted_messages[0]["_leaselab_original_text"] == text
        assert f"<@{identity.bot_user_id}>" in accepted_messages[0]["text"]

    anyio.run(scenario)


@pytest.mark.parametrize("change", ["duplicate_bot", "duplicate_app", "missing_role", "wrong_founder", "wrong_team", "missing_incidents", "duplicate_channel"])
def test_identity_map_fail_closed(change: str) -> None:
    body = MAP.model_dump()
    if change == "duplicate_bot":
        body["roles"]["sre"]["bot_user_id"] = body["roles"]["engineer"]["bot_user_id"]
    elif change == "duplicate_app":
        body["roles"]["sre"]["app_id"] = body["roles"]["engineer"]["app_id"]
    elif change == "missing_role":
        del body["roles"]["growth"]
    elif change == "wrong_founder":
        body["founder_user_id"] = "UOTHER"
    elif change == "wrong_team":
        body["team_id"] = "TOTHER"
    elif change == "duplicate_channel":
        body["channels"].append("C001")
    else:
        body["incident_channel_id"] = "COTHER"
    with pytest.raises(ValueError):
        Identities.model_validate(body)
