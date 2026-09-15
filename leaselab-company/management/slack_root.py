"""Verify recovery targets against Slack using the native profile secret scope."""

import re

from agent.secret_scope import get_secret
from pydantic import BaseModel, ConfigDict
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError, SlackRequestError

from .models import ManagementError
from .slack_directory import SlackDirectory


class RootMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    ts: str
    user: str = ""
    text: str = ""
    thread_ts: str = ""


class History(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    ok: bool
    messages: list[RootMessage]


def read_root(channel: str, timestamp: str) -> History:
    """Bounded exact-timestamp native SDK lookup; never return/log credentials."""
    token = get_secret("SLACK_BOT_TOKEN", "")
    if not token:
        raise ManagementError("CoS Slack credential unavailable for root verification")
    try:
        client = WebClient(token=token, timeout=15, retry_handlers=[])
        response = client.conversations_history(
            channel=channel, oldest=timestamp, latest=timestamp, inclusive=True, limit=1
        )
        return History.model_validate(response.data)
    except (SlackApiError, SlackRequestError, OSError, ValueError) as exc:
        raise ManagementError(
            "Slack root verification unavailable; keep incident blocked for reconciliation"
        ) from exc


def verify_root(
    target: str, directory: SlackDirectory, incident: str, parent: str
) -> None:
    """Require the exact CoS-authored root to attest both incident and Kanban ID."""
    _, channel, timestamp = target.split(":")
    if channel != directory.incident_channel_id:
        raise ManagementError("Recovery target must be in #incidents")
    history = read_root(channel, timestamp)
    if not history.ok or len(history.messages) != 1:
        raise ManagementError(
            "Slack incident root missing or ambiguous; no participants released"
        )
    root = history.messages[0]
    if (
        root.ts != timestamp
        or root.thread_ts not in ("", timestamp)
        or root.user != directory.roles["chief-of-staff"].bot_user_id
        or re.search(
            r"(?<![A-Z0-9-])" + re.escape(incident) + r"(?![A-Z0-9-])", root.text
        )
        is None
        or re.search(
            r"Authoritative Kanban:\s*" + re.escape(parent) + r"(?![A-Za-z0-9_])",
            root.text,
        )
        is None
    ):
        raise ManagementError(
            "Slack root does not attest this incident, Kanban parent and CoS author; no participants released"
        )
