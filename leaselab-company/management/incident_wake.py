"""Native durable CoS wake subscriptions; no polling loop or secondary queue."""

from contextlib import closing

from hermes_cli.kanban_db_connect import connect
from hermes_cli.kanban_db_notify import add_notify_sub, list_notify_subs
from pydantic import BaseModel, ConfigDict

from .models import IncidentUpdate, ManagementError
from .native import BOARD, Board
from .records import current_record
from .slack_directory import load_directory
from .slack_root import verify_root


class Subscription(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    platform: str
    chat_id: str
    thread_id: str
    user_id: str | None = None
    notifier_profile: str | None = None


def subscribe_verified_thread(board: Board, task_id: str, target: str) -> None:
    """Attach only the fixed Founder/CoS destination to a previously verified root."""
    checked = IncidentUpdate(slack_thread=target)
    if not checked.slack_thread:
        raise ManagementError(
            "A verified incident thread is required before subscription"
        )
    _, channel, timestamp = checked.slack_thread.split(":")
    directory = load_directory()
    if channel != directory.incident_channel_id:
        raise ManagementError(
            "Incident wake must target the configured #incidents channel"
        )
    with closing(connect(db_path=board.path, board=BOARD)) as conn:
        for raw in list_notify_subs(conn, task_id):
            sub = Subscription.model_validate(raw)
            if (
                sub.platform == "slack"
                and sub.chat_id == channel
                and sub.thread_id == timestamp
                and (
                    sub.user_id != "U0225R7NP8Q"
                    or sub.notifier_profile != "chief-of-staff"
                )
            ):
                raise ManagementError(
                    "Conflicting incident subscription requires explicit repair"
                )
        add_notify_sub(
            conn,
            task_id=task_id,
            platform="slack",
            chat_id=channel,
            thread_id=timestamp,
            user_id="U0225R7NP8Q",
            chat_type="group",
            notifier_profile="chief-of-staff",
            delivery_mode="wake",
            delivery_metadata={
                "scope_id": directory.team_id,
                "thread_id": timestamp,
                "chat_type": "group",
            },
        )


def repair_incident_wakes(board: Board, parent_id: str) -> list[str]:
    """Verify an existing root and subscribe its current native cards idempotently."""
    record = current_record(board, parent_id)
    if record.record_type != "incident":
        raise ManagementError("An incident parent is required")
    target = IncidentUpdate(slack_thread=record.slack_thread).slack_thread
    if not target:
        raise ManagementError("Incident root receipt required")
    verify_root(target, load_directory(), record.identity, parent_id)
    prefix = f"incident:{record.identity}:"
    tasks = [
        parent_id,
        *(
            task.id
            for task in board.tasks()
            if (task.idempotency_key or "").startswith(prefix)
        ),
    ]
    for task_id in tasks:
        subscribe_verified_thread(board, task_id, target)
    return tasks
