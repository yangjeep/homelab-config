"""Veto tools outside native role policy; SSH accounts supply the OS boundary."""

import logging
import os
import re
import stat
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final, Literal, Protocol, TypedDict, TypeVar

from pydantic import ConfigDict, JsonValue, TypeAdapter

LEARNING: Final = frozenset(
    {"memory", "skills_list", "skill_view", "skill_manage", "session_search"}
)
WORKER_KANBAN: Final = frozenset(
    {
        "kanban_show",
        "kanban_complete",
        "kanban_block",
        "kanban_request_review",
        "kanban_request_changes",
        "kanban_heartbeat",
        "kanban_comment",
        "kanban_attach",
        "kanban_attach_url",
        "kanban_attachments",
        "kanban_link",
    }
)
COS_KANBAN: Final = WORKER_KANBAN | {"kanban_list", "kanban_unblock", "kanban_create"}
SSH_TOOLS: Final = frozenset(
    {"terminal", "read_file", "write_file", "patch", "search_files"}
)
ROLE_TOOLS: Final = {
    "chief-of-staff": LEARNING | COS_KANBAN | {"company_github", "company_management"},
    "support": LEARNING | WORKER_KANBAN | SSH_TOOLS | {"company_request_coordination"},
    "sre": LEARNING | WORKER_KANBAN | SSH_TOOLS | {"company_request_coordination"},
    "engineer": LEARNING | WORKER_KANBAN | SSH_TOOLS | {"company_request_coordination"},
    "reviewer": LEARNING | WORKER_KANBAN | SSH_TOOLS | {"company_request_coordination"},
    "qa-security": LEARNING
    | WORKER_KANBAN
    | SSH_TOOLS
    | {"company_request_coordination"},
    "growth": LEARNING | WORKER_KANBAN | SSH_TOOLS | {"company_request_coordination"},
}
LOGGER: Final = logging.getLogger(__name__)
SLACK_CHANNEL_ROLES: Final = {
    "C0C2Q3Y1QF2": frozenset({"chief-of-staff"}),
    "C0C2Q43J0KS": frozenset({"chief-of-staff", "engineer", "reviewer", "qa-security"}),
    "C0C1XMT2BU1": frozenset({"chief-of-staff", "engineer", "reviewer", "qa-security"}),
    "C0C1PH369DH": frozenset({"chief-of-staff", "sre", "qa-security", "support"}),
    "C0C1XMYQMR7": frozenset({"chief-of-staff", "support", "sre", "engineer"}),
    "C0C1R45U8SH": frozenset({"chief-of-staff", "growth", "engineer"}),
}
SLACK_IDENTITIES: Final = Path("/etc/leaselab-company/slack-identities.json")
IDENTITY_DATA: Final = TypeAdapter(
    dict[str, JsonValue], config=ConfigDict(hide_input_in_errors=True)
)
SLACK_TARGET: Final = re.compile(r"slack:(C[A-Z0-9]+)(?::[0-9]{10}\.[0-9]{6})?")


class BlockDirective(TypedDict):
    action: Literal["block"]
    message: str


Registration_co = TypeVar("Registration_co", covariant=True)
HookValue = str | int | float | bool | None | list["HookValue"] | dict[str, "HookValue"]


class HookContext(Protocol[Registration_co]):
    def register_hook(
        self, hook_name: str, callback: Callable[..., BlockDirective | None]
    ) -> Registration_co: ...

    def register_tool(
        self,
        *,
        name: str,
        toolset: str,
        schema: Mapping[str, HookValue],
        handler: Callable[..., str],
    ) -> Registration_co: ...


def _terminal_config() -> Mapping[str, str | int]:
    """Read the effective native scope, including config-to-environment bridging."""
    from tools.terminal_tool import _get_env_config

    config = _get_env_config()
    return {
        key: config[key]
        for key in ("env_type", "ssh_host", "ssh_user", "ssh_port", "ssh_key")
    }


def _incident_channel_allowed(channel: str) -> bool:
    """Only root-managed workspace mapping may extend fixed sender destinations."""
    try:
        descriptor = os.open(SLACK_IDENTITIES, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor) as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or info.st_mode & 0o022
            ):
                return False
            data = IDENTITY_DATA.validate_json(handle.read())
        channels = data.get("channels")
        return (
            data.get("team_id") == "T021CUR5KTP"
            and data.get("founder_user_id") == "U0225R7NP8Q"
            and data.get("incident_channel_id") == channel
            and isinstance(channels, list)
            and channel in channels
        )
    except (OSError, ValueError):
        return False


def _slack_send_allowed(role: str, args: HookValue) -> bool:
    """Allow only attributed text to explicit company channels and Slack threads."""
    if not isinstance(args, dict) or set(args) - {"action", "target", "message"}:
        return False
    if args.get("action", "send") != "send":
        return False
    target, message = args.get("target"), args.get("message")
    if not isinstance(target, str) or not isinstance(message, str):
        return False
    destination = SLACK_TARGET.fullmatch(target)
    return bool(
        destination
        and role in ROLE_TOOLS
        and (
            role in SLACK_CHANNEL_ROLES.get(destination[1], frozenset())
            or _incident_channel_allowed(destination[1])
        )
        and message.strip()
        # Native send_message extracts local files from MEDIA directives.
        and re.search("MEDIA:", message, re.IGNORECASE) is None
        and "[[as_document]]" not in message
        and "[[audio_as_voice]]" not in message
    )


def _founder_notify_allowed(role: str, args: HookValue) -> bool:
    if (
        role != "chief-of-staff"
        or not isinstance(args, dict)
        or set(args) != {"message"}
    ):
        return False
    message = args["message"]
    prefix = "[Chief of Staff] "
    return bool(
        isinstance(message, str)
        and len(message) <= 3000
        and message.startswith(prefix)
        and message[len(prefix) :].strip()
        and re.search("MEDIA:", message, re.IGNORECASE) is None
        and not any(
            marker in message.casefold()
            for marker in ("[[as_document]]", "[[audio_as_voice]]", "\x00")
        )
    )


def _session_search_allowed(role: str, args: HookValue) -> bool:
    if not isinstance(args, dict) or set(args) - {
        "query",
        "limit",
        "sort",
        "detail",
        "session_id",
        "around_message_id",
        "window",
        "role_filter",
        "profile",
    }:
        return False
    if "profile" in args and args["profile"] != role:
        return False
    if "session_id" not in args:
        return True
    session_id = args["session_id"]
    if not isinstance(session_id, str):
        return False
    if "/" in session_id:
        embedded_profile, _, session_id = session_id.partition("/")
        if embedded_profile != role:
            return False
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", session_id) is not None


def pre_tool_call(
    tool_name: str, args: HookValue = None, **_kwargs: HookValue
) -> BlockDirective | None:
    """Veto unsafe assignments and execution before native tool dispatch."""
    role = os.environ.get("HERMES_PROFILE", "")
    if tool_name == "send_message" and _slack_send_allowed(role, args):
        return None
    if tool_name == "company_founder_notify" and _founder_notify_allowed(role, args):
        return None
    permitted = ROLE_TOOLS.get(role, frozenset())
    if type(tool_name) is str and tool_name in permitted:
        if tool_name == "session_search":
            if _session_search_allowed(role, args):
                return None
            return {
                "action": "block",
                "message": "Session selector denied by company profile policy.",
            }
        if tool_name == "kanban_create":
            # Native hooks receive arbitrary JSON; reject malformed values before lookup.
            if isinstance(args, dict):
                assignee = args.get("assignee")
                if isinstance(assignee, str) and assignee in ROLE_TOOLS:
                    return None
            return {
                "action": "block",
                "message": "Task assignee denied by company policy.",
            }
        if tool_name not in SSH_TOOLS:
            return None
        try:
            config = _terminal_config()
            if (
                config.get("env_type") == "ssh"
                and config.get("ssh_host") == "127.0.0.1"
                and config.get("ssh_user") == f"leaselab-{role}"
                and type(config.get("ssh_port")) is int
                and config.get("ssh_port") == 22
                and config.get("ssh_key") == f"/etc/leaselab-company/ssh/{role}"
            ):
                return None
        except Exception:  # noqa: BLE001 -- native hook errors fail open. # noqa: BROAD_EXCEPT_OK
            LOGGER.warning("Company guard denied an unavailable terminal policy")
    return {"action": "block", "message": "Tool denied by company role policy."}


def register(ctx: HookContext[Registration_co]) -> None:
    """Install the native permission callback for this trusted profile process."""
    _ = ctx.register_hook("pre_tool_call", pre_tool_call)
    _ = ctx.register_tool(
        name="send_message",
        toolset="leaselab-slack-send",
        handler=_send_slack_native,
        schema={
            "name": "send_message",
            "description": "Post plain text using your own Slack identity to an authorized LeaseLab Slack channel or thread. Kanban and GitHub remain authoritative.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string", "enum": ["send"]},
                    "target": {
                        "type": "string",
                        "description": "Exact slack:C... channel ID, optionally followed by :<thread timestamp>.",
                    },
                    "message": {
                        "type": "string",
                        "description": "Nonempty plain text; no media directives or identity overrides.",
                    },
                },
                "required": ["target", "message"],
            },
        },
    )

    if os.environ.get("HERMES_PROFILE") == "chief-of-staff":
        _ = ctx.register_tool(
            name="company_founder_notify",
            toolset="leaselab-slack-send",
            handler=_notify_founder_native,
            schema={
                "name": "company_founder_notify",
                "description": "Notify the verified Founder privately on Telegram, only for production outage, data-loss or destructive-migration risk, P0/release-blocking P1, rollback, credential or Founder-decision blockers, or important production completion. Routine PR/test/QA/merge/deploy updates belong in Slack or a digest. One fixed recipient; text only.",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "message": {
                            "type": "string",
                            "maxLength": 3000,
                            "description": "Nonempty plain text starting with [Chief of Staff] ; no media directives or secrets.",
                        }
                    },
                    "required": ["message"],
                },
            },
        )


def _notify_founder_native(args: HookValue, **_kwargs: HookValue) -> str:
    if not _founder_notify_allowed(os.environ.get("HERMES_PROFILE", ""), args):
        return '{"error":"Founder notification denied by company role policy."}'
    assert isinstance(args, dict)
    from tools.send_message_tool import send_message_tool

    return send_message_tool(
        {
            "action": "send",
            "target": "telegram:660328434",
            "message": args["message"],
        }
    )


def _send_slack_native(args: HookValue, **_kwargs: HookValue) -> str:
    """Apply the same boundary even if called outside the pre-tool hook path."""
    if not _slack_send_allowed(os.environ.get("HERMES_PROFILE", ""), args):
        return '{"error":"Slack send denied by company role policy."}'
    from tools.send_message_tool import send_message_tool

    return send_message_tool(args)
