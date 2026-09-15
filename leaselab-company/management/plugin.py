"""Role-pinned native tools for management and specialist escalation."""

import hashlib
import json
import os
from datetime import datetime
from typing import assert_never
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from .models import ROLES, CoordinationRequest, ManagementRequest
from .native import Board, Card
from .records import update_incident
from .session_context import coordination_origin, slack_conversation
from .slack_directory import load_directory
from .workflow import (
    close_incident,
    close_weekly,
    start_incident,
    start_weekly,
    summary_context,
)

Value = str | int | float | bool | None | list["Value"] | dict[str, "Value"]


def company_management(args: Value, **_kwargs: Value) -> str:
    """Only the CoS profile can create team assignments or close incidents."""
    if os.environ.get("HERMES_PROFILE") != "chief-of-staff":
        return '{"error":"CoS management authority required"}'
    try:
        request = ManagementRequest.model_validate(args)
        board = Board()
        match request.action:
            case "team_status":
                directory = load_directory()
                conversation = slack_conversation(directory)
                return json.dumps(
                    {
                        "tasks": [
                            task.model_dump(mode="json") for task in board.tasks()
                        ],
                        "slack": directory.model_dump(mode="json"),
                        "conversation": conversation.model_dump(mode="json")
                        if conversation
                        else None,
                    }
                )
            case "weekly_start":
                week = request.week or datetime.now(
                    ZoneInfo("America/Toronto")
                ).strftime("%G-W%V")
                if request.questions is None and not any(
                    task.idempotency_key == f"management:{week}"
                    for task in board.tasks()
                ):
                    return '{"error":"Read team_status, then supply evidence-grounded questions for all six roles"}'
                return start_weekly(board, week, request.questions).model_dump_json()
            case "summary_context":
                return summary_context(board, request.parent_id).model_dump_json()
            case "incident_start":
                if request.incident is None:
                    return '{"error":"incident contract required"}'
                return start_incident(board, request.incident).model_dump_json()
            case "incident_update":
                if request.checkpoint is None:
                    return '{"error":"checkpoint required"}'
                return update_incident(
                    board, request.parent_id, request.checkpoint
                ).model_dump_json()
            case "weekly_close":
                close_weekly(board, request.parent_id, request.summary)
                return '{"status":"closed"}'
            case "incident_close":
                close_incident(
                    board, request.parent_id, request.resolution, request.verification
                )
                return '{"status":"closed"}'
            case _:
                assert_never(request.action)
    except ValidationError as exc:
        return json.dumps(
            {
                "error": "Management validation failed",
                "fields": [
                    {
                        "path": ".".join(str(part) for part in error["loc"]),
                        "rule": error["type"],
                    }
                    for error in exc.errors(
                        include_input=False, include_context=False, include_url=False
                    )
                ],
                "hint": "Omit week for the current Toronto week, or use YYYY-Www. Each role question must contain 10 to 2000 characters.",
            }
        )
    except (ValueError, OSError):
        return '{"error":"Invalid management request or incomplete evidence; inspect native task state"}'


def company_request_coordination(args: Value, **_kwargs: Value) -> str:
    """A specialist may request CoS triage, never select another role's tools."""
    role = os.environ.get("HERMES_PROFILE", "")
    if role not in ROLES:
        return '{"error":"Specialist identity required"}'
    try:
        request = CoordinationRequest.model_validate(args)
    except ValidationError:
        return '{"error":"Provide only intent; routing is derived automatically from the native session"}'
    try:
        board = Board()
        origin = coordination_origin(board, load_directory())
    except (ValueError, OSError):
        return '{"error":"An authorized native session is required for coordination"}'
    digest = hashlib.sha256(origin.source_ref.encode()).hexdigest()
    task_id = board.create(
        Card(
            "CoS coordination intake",
            f"Submitted by {role}; source {origin.source_ref}.\nIntent: {request.intent}\n"
            "CoS owns orchestration. Determine primary owner and participating roles; use company_management "
            "incident_start for cross-role P0/P1, otherwise native Kanban parent/dependencies. Attach GitHub issue "
            "before nontrivial engineering. Inspect any existing intake for this source; do not duplicate fixes. "
            "Create Slack coordination thread and concise shared evidence; existing release gates apply.",
            "chief-of-staff",
            f"coordination:{digest}",
            author=role,
            priority=1,
        )
    )
    return json.dumps(
        {
            "task_id": task_id,
            "assignee": "chief-of-staff",
            "thread_root": origin.thread_root,
            "channel": origin.channel,
        }
    )
