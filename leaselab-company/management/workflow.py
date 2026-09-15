"""CoS orchestration using native Kanban dependency and retry semantics."""

from datetime import datetime, timezone

from .incident_notification import ensure_incident_thread, incident_lock
from .incident_roles import create_investigations
from .incident_wake import subscribe_verified_thread
from .models import (
    ROLES,
    TOPICS,
    Cycle,
    Evidence,
    IncidentRequest,
    ManagementError,
    Questions,
    Record,
)
from .native import Board, Card
from .records import current_record


def start_weekly(board: Board, week: str, questions: Questions | None = None) -> Cycle:
    """Resume one ISO-week cycle, independently dispatching each interview."""
    record = Record(
        record_type="weekly_management",
        identity=week,
        started_at=datetime.now(timezone.utc).isoformat(),
        participants=list(ROLES),
        question_plan=questions.model_dump_json(by_alias=True) if questions else "",
    )
    parent = board.create(
        Card(
            f"Weekly management {week}",
            record.model_dump_json(),
            "chief-of-staff",
            f"management:{week}",
            status="blocked",
        )
    )
    persisted = current_record(board, parent)
    if persisted.question_plan:
        questions = Questions.model_validate_json(persisted.question_plan)
    tasks = board.tasks()
    children: list[str] = []
    for role in ROLES:
        work = [
            task.model_dump(mode="json")
            for task in tasks
            if task.assignee == role
            and not (task.idempotency_key or "").startswith("management:")
        ]
        prior = [
            task.model_dump(mode="json")
            for task in tasks
            if task.assignee == role
            and (task.idempotency_key or "").startswith("management:")
            and task.status == "done"
        ][-4:]
        body = (
            f"CoS operational 1:1 with {role}, ISO week {week}. Management parent: {parent}.\n"
            f"Role topics: {TOPICS[role]}\n"
            f"CoS questions: {questions.for_role(role) if questions else 'Synthetic library validation: inspect only fixture evidence'}\n"
            f"Observed native current work snapshot: {work}\nPrevious concise notes: {prior}\n"
            "Refresh Kanban and consult linked GitHub/QA/deployment/security artifacts through your allowed tools. "
            "Choose questions based on current evidence and unresolved previous friction, not a fixed questionnaire. "
            "Distinguish self-report from independently verified evidence; absent data means unknown, not zero activity. "
            "Return a concise structured note: Role, Current focus, Shipped (evidence links), Open work, Blockers, "
            "Recurring friction, Handoff quality, Security/reliability, Workload, Suggested improvement, Manager action. "
            "Include evidence references for every factual claim. One-off friction is not automatically a new issue. "
            "Confirmed security findings remain P0/P1 bugs. Do not implement changes during this interview. "
            "Finish using native kanban_complete with this concise note as result/summary. If unavailable, "
            "record reason in native task state; native independent retries remain bounded at three."
        )
        children.append(
            board.create(
                Card(
                    f"Weekly 1:1 {role} {week}",
                    body,
                    role,
                    f"management:{week}:{role}",
                    creator=parent,
                )
            )
        )
    summary = board.create(
        Card(
            f"Weekly Management Summary {week}",
            f"Call company_management action=summary_context parent_id={parent}. Read all six current notes and "
            "their original evidence; consult previous notes for repeated patterns. Produce LeaseLab Weekly Management "
            "Summary: TL;DR, Team status, What shipped, What improved, Recurring problems, Cross-team friction, "
            "Security/reliability, Workload imbalance, Automation opportunities, Decisions needed, Next-week priorities. "
            "Do not fabricate activity or claim causality from one report. Persist the concise summary using native "
            "kanban_complete. Use company_management weekly_close on the parent with the evidence-based summary. "
            "Send one concise Founder Telegram weekly TL;DR using company_founder_notify; only material decisions "
            "need expanded context/options/consequence/recommendation. No transcripts or secrets.",
            "chief-of-staff",
            f"management:{week}:summary",
            tuple(children),
            creator=parent,
        )
    )
    return Cycle(
        parent=parent,
        children=children,
        summary=summary,
        assignments=dict(zip(ROLES, children, strict=True)),
    )


def summary_context(board: Board, parent_id: str) -> Evidence:
    """Return current native evidence, including explicit incomplete interviews."""
    record = current_record(board, parent_id)
    prefix = (
        f"management:{record.identity}:"
        if record.record_type == "weekly_management"
        else f"incident:{record.identity}:"
    )
    tasks = board.tasks()
    children = [
        task
        for task in tasks
        if (task.idempotency_key or "").startswith(prefix)
        and task.idempotency_key != f"{prefix}summary"
    ]
    return Evidence(
        parent=parent_id,
        completed=[task for task in children if task.status == "done"],
        incomplete=[task for task in children if task.status != "done"],
        current_work=[
            task
            for task in tasks
            if not (task.idempotency_key or "").startswith(("management:", "incident:"))
        ],
        prior_notes=[
            task
            for task in tasks
            if (task.idempotency_key or "").startswith("management:")
            and not (task.idempotency_key or "").startswith(prefix)
            and task.status == "done"
        ][-30:],
    )


def start_incident(board: Board, request: IncidentRequest) -> Cycle:
    """Serialize receipt establishment and idempotent participant creation."""
    with incident_lock(board):
        return _start_incident(board, request)


def _start_incident(board: Board, request: IncidentRequest) -> Cycle:
    """Persist an incident and separate investigations without release authority."""
    record = Record(
        record_type="incident",
        identity=request.incident_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        severity=request.severity,
        primary_owner=request.primary_owner,
        participants=list(request.participants),
        impact=request.impact,
        github_links=request.github_links,
        slack_thread=request.slack_thread,
        synthetic=request.synthetic,
    )
    prefix = f"incident:{request.incident_id}"
    priority = 2 if request.severity == "P0" else 1
    parent = board.create(
        Card(
            f"{request.severity} {request.incident_id}",
            record.model_dump_json(),
            "chief-of-staff",
            prefix,
            status="blocked",
            priority=priority,
        )
    )
    thread = ensure_incident_thread(board, parent, request)
    subscribe_verified_thread(board, parent, thread)
    request = request.model_copy(update={"slack_thread": thread})
    assignments = create_investigations(board, request, parent)
    children = [assignments[role] for role in request.participants]
    summary = board.create(
        Card(
            f"{request.incident_id} verify resolution",
            f"Call company_management summary_context parent_id={parent}; review all participant evidence and "
            "shared #incidents thread. Require mitigation, resolution and independent verification. If incomplete "
            "or still impacted keep incident open. Otherwise use company_management incident_close with actual "
            "resolution and verification, then post concise Slack/Founder material update. Do not infer recovery.",
            "chief-of-staff",
            f"{prefix}:summary",
            tuple(children),
            creator=parent,
            priority=priority,
        )
    )
    for task_id in [*children, summary]:
        subscribe_verified_thread(board, task_id, thread)
    return Cycle(
        parent=parent,
        children=children,
        summary=summary,
        assignments=assignments,
        slack_thread=thread,
    )


def close_incident(
    board: Board, parent_id: str, resolution: str, verification: str
) -> None:
    """Gate closure on durable participant completion plus explicit verification."""
    record = current_record(board, parent_id)
    evidence = summary_context(board, parent_id)
    observed = [task.assignee for task in evidence.completed]
    if (
        record.record_type != "incident"
        or evidence.incomplete
        or set(observed) != set(record.participants)
        or len(observed) != len(record.participants)
    ):
        raise ManagementError("Incident participants incomplete or invalid parent")
    if not resolution.strip() or not verification.strip():
        raise ManagementError("Resolution and verification evidence required")
    closed = record.model_copy(
        update={
            "status": "closed",
            "resolution": resolution,
            "verification": verification,
        }
    )
    board.comment(parent_id, closed.model_dump_json())
    if not board.complete(parent_id, closed.model_dump_json()):
        raise ManagementError("Native incident completion refused")


def close_weekly(board: Board, parent_id: str, summary: str) -> None:
    """Close the management anchor only after six genuine interview completions."""
    record = current_record(board, parent_id)
    evidence = summary_context(board, parent_id)
    observed = [task.assignee for task in evidence.completed]
    if (
        record.record_type != "weekly_management"
        or evidence.incomplete
        or set(observed) != set(ROLES)
        or len(observed) != len(ROLES)
        or not summary.strip()
    ):
        raise ManagementError("Weekly interviews incomplete or summary missing")
    if not board.complete(parent_id, summary):
        raise ManagementError("Native weekly completion refused")
