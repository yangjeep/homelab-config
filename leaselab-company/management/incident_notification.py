"""Native Slack receipt checkpoint; uncertain delivery never triggers blind resend."""

import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from tools.send_message_tool import send_message_tool

from .models import IncidentRequest, ManagementError
from .native import Board
from .records import current_record
from .slack_directory import load_directory
from .slack_root import verify_root


class Receipt(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    success: bool = False
    message_id: str = Field(default="", pattern=r"^(?:[0-9]{10}\.[0-9]{6})?$")


@contextmanager
def incident_lock(board: Board) -> Generator[None]:
    """Serialize CoS gateway/dispatcher attempts without another state database."""
    path = board.path or Path(
        "/var/lib/leaselab-company/kanban/boards/leaselab-company/kanban.db"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".incident.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ManagementError(
                "Another incident operation is active; retry after it finishes"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def ensure_incident_thread(board: Board, parent: str, request: IncidentRequest) -> str:
    """Persist attempt before native transport, receipt before role dispatch."""
    directory = load_directory()
    current = current_record(board, parent)
    if (
        current.participants != request.participants
        or current.primary_owner != request.primary_owner
        or current.severity != request.severity
        or current.impact != request.impact
        or current.github_links != request.github_links
        or current.synthetic != request.synthetic
    ):
        raise ManagementError(
            "Existing incident contract differs; resume its original contract"
        )
    supplied = request.slack_thread
    if supplied and supplied.split(":")[1] != directory.incident_channel_id:
        raise ManagementError(
            "Use the actual #incidents thread destination; provenance is not a send target"
        )
    if current.notification_state == "sent":
        if supplied and supplied != current.slack_thread:
            raise ManagementError(
                "Incident already has a different canonical thread; reuse its receipt"
            )
        verify_root(current.slack_thread, directory, current.identity, parent)
        return current.slack_thread
    # A valid target is explicit authorized reconciliation; historical malformed values are never inferred.
    if supplied:
        verify_root(supplied, directory, current.identity, parent)
        recovered = current.model_copy(
            update={
                "slack_thread": supplied,
                "notification_state": "sent",
            }
        )
        board.comment(parent, recovered.model_dump_json())
        return supplied
    if current.slack_thread or current.notification_state != "idle":
        raise ManagementError(
            f"Incident {parent} requires delivery reconciliation: inspect #incidents and resume with its actual slack_thread; do not resend blindly"
        )
    pending = current.model_copy(update={"notification_state": "pending"})
    board.comment(parent, pending.model_dump_json())
    mentions = " ".join(
        f"<@{directory.roles[role].bot_user_id}>" for role in current.participants
    )
    primary = directory.roles[current.primary_owner].bot_user_id
    message = (
        f"{current.severity} — {current.identity}"
        + (" — SYNTHETIC DRILL" if current.synthetic else "")
        + f"\nImpact: {current.impact}\nPrimary owner: <@{primary}>\nParticipants: {mentions}"
        + f"\nKnown state: {current.current_hypothesis}\nCurrent action: {current.current_action}"
        + f"\nAuthoritative Kanban: {parent}\nGitHub: {', '.join(current.github_links) or 'none yet'}"
        + "\nRole assignments follow the persisted Slack receipt. Existing QA/Reviewer/SRE gates apply."
    )
    try:
        receipt = Receipt.model_validate_json(
            send_message_tool(
                {
                    "action": "send",
                    "target": f"slack:{directory.incident_channel_id}",
                    "message": message,
                }
            )
        )
        if not receipt.success or not receipt.message_id:
            raise ManagementError(
                "Native send did not return a successful Slack receipt"
            )
    except (ValueError, OSError) as exc:
        board.comment(
            parent,
            pending.model_copy(
                update={"notification_state": "reconciliation"}
            ).model_dump_json(),
        )
        raise ManagementError(
            f"Incident {parent} delivery is uncertain; inspect #incidents and resume with its actual slack_thread; no participants released"
        ) from exc
    target = f"slack:{directory.incident_channel_id}:{receipt.message_id}"
    board.comment(
        parent,
        pending.model_copy(
            update={
                "slack_thread": target,
                "notification_state": "sent",
            }
        ).model_dump_json(),
    )
    return target
