"""Obtain routing provenance from Hermes task-local session context, never prose."""

import os
import re

from gateway.session_context import get_session_env

from .models import ManagementError, Model
from .native import Board
from .slack_directory import SlackDirectory


class Conversation(Model):
    source_ref: str
    channel: str = ""
    message_id: str = ""
    thread_root: str = ""
    platform: str
    user_id: str = ""
    scope_id: str = ""


def slack_conversation(directory: SlackDirectory) -> Conversation | None:
    """Validate the native session against the one authorized workspace/founder."""
    if get_session_env("HERMES_SESSION_PLATFORM") != "slack":
        return None
    channel = get_session_env("HERMES_SESSION_CHAT_ID")
    message_id = get_session_env("HERMES_SESSION_MESSAGE_ID")
    thread_root = get_session_env("HERMES_SESSION_THREAD_ID") or message_id
    scope = get_session_env("HERMES_SESSION_SCOPE_ID")
    user = get_session_env("HERMES_SESSION_USER_ID")
    if (
        scope != directory.team_id
        or user != "U0225R7NP8Q"
        or channel not in directory.channels
        or not re.fullmatch(r"[0-9]+\.[0-9]+", message_id)
        or not re.fullmatch(r"[0-9]+\.[0-9]+", thread_root)
    ):
        raise ManagementError("Slack session provenance is not authorized")
    return Conversation(
        source_ref=f"slack:{scope}:{channel}:{message_id}",
        channel=channel,
        message_id=message_id,
        thread_root=thread_root,
        platform="slack",
        user_id=user,
        scope_id=scope,
    )


def coordination_origin(board: Board, directory: SlackDirectory) -> Conversation:
    """Allow Founder Slack or the invoking specialist's native running task."""
    conversation = slack_conversation(directory)
    if conversation is not None:
        return conversation
    task_id = os.environ.get("HERMES_KANBAN_TASK", "")
    if not re.fullmatch(r"t_[0-9a-f]+", task_id):
        raise ManagementError("Native Slack or assigned Kanban context required")
    task = board.task(task_id)
    if task.assignee != os.environ.get("HERMES_PROFILE") or task.status != "running":
        raise ManagementError("Kanban context does not belong to invoking specialist")
    return Conversation(source_ref=f"kanban:{task_id}", platform="kanban")
