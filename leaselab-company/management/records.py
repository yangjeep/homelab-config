"""Durable CoS-authored checkpoints in native Kanban comments."""

from pydantic import ValidationError

from .models import IncidentUpdate, ManagementError, Record
from .native import Board


def current_record(board: Board, parent_id: str) -> Record:
    """Recover the latest CoS checkpoint from native comments after restart."""
    original = Record.model_validate_json(board.task(parent_id).body or "")
    for body in reversed(board.comments(parent_id)):
        try:
            candidate = Record.model_validate_json(body)
        except ValidationError:
            continue
        if (
            candidate.identity == original.identity
            and candidate.record_type == original.record_type
            and candidate.participants == original.participants
            and candidate.primary_owner == original.primary_owner
            and candidate.severity == original.severity
        ):
            return candidate
    return original


def update_incident(board: Board, parent_id: str, update: IncidentUpdate) -> Record:
    """Append a durable checkpoint without changing ownership or bypassing closure."""
    current = current_record(board, parent_id)
    if current.record_type != "incident" or current.status == "closed":
        raise ManagementError("An open incident is required")
    if (
        current.notification_state == "sent"
        and update.slack_thread
        and update.slack_thread != current.slack_thread
    ):
        raise ManagementError(
            "Incident already has a different canonical thread; reuse its receipt"
        )
    fields = update.model_dump(exclude_unset=True)
    if not update.slack_thread:
        fields.pop("slack_thread", None)
    changed = current.model_copy(update=fields)
    board.comment(parent_id, changed.model_dump_json())
    return changed
