"""Veto tools outside native role policy; SSH accounts supply the OS boundary."""

import logging
import os
import re
from collections.abc import Callable, Mapping
from typing import Final, Literal, Protocol, TypedDict, TypeVar

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
    "chief-of-staff": LEARNING | COS_KANBAN | {"company_github"},
    "support": LEARNING | WORKER_KANBAN | SSH_TOOLS,
    "sre": LEARNING | WORKER_KANBAN | SSH_TOOLS,
    "engineer": LEARNING | WORKER_KANBAN | SSH_TOOLS,
    "reviewer": LEARNING | WORKER_KANBAN | SSH_TOOLS,
    "qa-security": LEARNING | WORKER_KANBAN | SSH_TOOLS,
    "growth": LEARNING | WORKER_KANBAN | SSH_TOOLS,
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
SLACK_PREFIXES: Final = {
    "chief-of-staff": "[Chief of Staff] ",
    "engineer": "[Engineer] ",
    "reviewer": "[Reviewer] ",
    "qa-security": "[QA/Security] ",
    "sre": "[SRE] ",
    "support": "[Support] ",
    "growth": "[Growth] ",
}
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
    prefix = SLACK_PREFIXES.get(role)
    return bool(
        destination
        and role in SLACK_CHANNEL_ROLES.get(destination[1], frozenset())
        and prefix
        and message.startswith(prefix)
        and message[len(prefix) :].strip()
        # Native send_message extracts local files from MEDIA directives.
        and "MEDIA:" not in message
        and "[[as_document]]" not in message
        and "[[audio_as_voice]]" not in message
    )


def pre_tool_call(
    tool_name: str, args: HookValue = None, **_kwargs: HookValue
) -> BlockDirective | None:
    """Veto unsafe assignments and execution before native tool dispatch."""
    role = os.environ.get("HERMES_PROFILE", "")
    if tool_name == "send_message" and _slack_send_allowed(role, args):
        return None
    permitted = ROLE_TOOLS.get(role, frozenset())
    if type(tool_name) is str and tool_name in permitted:
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
            "description": "Post role-prefixed plain text to an authorized LeaseLab Slack channel or thread. Kanban and GitHub remain authoritative.",
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
                        "description": "Plain text starting with your exact [Role] prefix; no media directives.",
                    },
                },
                "required": ["target", "message"],
            },
        },
    )


def _send_slack_native(args: HookValue, **_kwargs: HookValue) -> str:
    """Apply the same boundary even if called outside the pre-tool hook path."""
    if not _slack_send_allowed(os.environ.get("HERMES_PROFILE", ""), args):
        return '{"error":"Slack send denied by company role policy."}'
    from tools.send_message_tool import send_message_tool

    return send_message_tool(args)
