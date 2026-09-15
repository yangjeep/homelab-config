"""Distinct incident responsibilities with native evidence dependencies."""

from typing import Final

from .models import IncidentRequest, Role
from .native import Board, Card

SCOPES: Final[dict[Role, str]] = {
    "support": "Collect customer-impact and reproduction evidence with minimum necessary information. Do not start a parallel implementation.",
    "engineer": "Inspect application changes and isolate the code-level cause. Only the designated primary owner coordinates a fix; do not independently implement a duplicate change.",
    "qa-security": "Perform independent functional reproduction, regression and security verification against the primary owner's exact candidate/evidence. Source inspection alone is not functional QA. Missing access or test data is a blocker, not PASS.",
    "reviewer": "Perform independent code review of the exact candidate and inspect the QA evidence. Report blockers; this incident investigation card does not authorize merge or substitute for the existing merge gate.",
    "sre": "Inspect runtime, workflow, deployment and recovery evidence. Do not migrate or promote without the existing reviewed artifact and production gate.",
    "growth": "Inspect readonly analytics and public visibility impact. Do not modify tracking, content or infrastructure during investigation.",
}


def create_investigations(
    board: Board, request: IncidentRequest, parent: str
) -> dict[Role, str]:
    """Create primary first; QA consumes primary evidence and review consumes QA."""
    order: list[Role] = [request.primary_owner]
    order.extend(
        role
        for role in request.participants
        if role != request.primary_owner and role != "reviewer"
    )
    if "reviewer" in request.participants and request.primary_owner != "reviewer":
        order.append("reviewer")
    prerequisite_roles: dict[Role, Role] = {
        "qa-security": request.primary_owner,
        "reviewer": "qa-security"
        if "qa-security" in request.participants
        else request.primary_owner,
    }
    assignments: dict[Role, str] = {}
    safety = (
        "SYNTHETIC DRILL: fixture-only evidence; never access or mutate production. "
        if request.synthetic
        else "Existing QA/Reviewer/SRE gates remain mandatory. "
    )
    for role in order:
        predecessor = prerequisite_roles.get(role)
        prerequisites = (
            (assignments[predecessor],)
            if predecessor is not None
            and predecessor != role
            and role != request.primary_owner
            else ()
        )
        ownership = (
            "You are the sole primary technical owner for this incident: maintain one diagnosis and coordinated fix path. "
            if role == request.primary_owner
            else f"Primary technical owner is {request.primary_owner}; contribute distinct evidence to that owner. "
        )
        assignments[role] = board.create(
            Card(
                f"{request.incident_id} {role} investigation",
                f"{safety}{ownership}{SCOPES[role]} CoS incident parent: {parent}. "
                f"Impact: {request.impact}. Participants: {', '.join(request.participants)}. "
                f"GitHub evidence: {request.github_links}. Slack coordination: {request.slack_thread or 'CoS to attach'}. "
                "Read dependency results before acting. Record concise evidence, hypothesis, action, blockers and required handoffs on the parent. "
                "Nontrivial engineering requires an authoritative GitHub issue and assignment before implementation. "
                "Return verified findings and artifact references with native kanban_complete; urgency is not authorization.",
                role,
                f"incident:{request.incident_id}:{role}",
                prerequisites=prerequisites,
                creator=parent,
                priority=2 if request.severity == "P0" else 1,
            )
        )
    return assignments
