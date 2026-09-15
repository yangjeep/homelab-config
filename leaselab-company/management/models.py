"""Typed management contracts stored in native Kanban bodies and handoffs."""

from typing import Final, Literal, assert_never

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Role = Literal["support", "sre", "engineer", "reviewer", "qa-security", "growth"]
ROLES: Final[tuple[Role, ...]] = (
    "support",
    "sre",
    "engineer",
    "reviewer",
    "qa-security",
    "growth",
)
TOPICS: Final[dict[Role, str]] = {
    "engineer": "Open implementation, stale PRs, repeated CI failures, architecture friction, unclear contracts, QA rejection/rework, tooling and materially costly debt.",
    "qa-security": "Recurring regression, tenant isolation, confirmed security bugs (P0 or P1), false positives/negatives, missing tests, Engineer handoff quality, weak or expensive release gates.",
    "reviewer": "Recurring code quality, ambiguous contracts, QA disagreement, merge/re-review friction, complexity, patterns worth guidance. Escalate product ambiguity; do not change intent.",
    "sre": "Deployments, rollback, migrations, workflows, backups, toil, observability, provider instability, capacity/rate limits, credentials and recovery. What required unnecessary human attention?",
    "support": "Repeated customer problems, escalation evidence, product defects, slow investigations, tooling and unnecessary customer-data exposure. Do not turn every request into engineering.",
    "growth": "Experiments and useful signals, GA4/Search Console, SEO/GEO/content gaps, engineering waits, recurring research, competitors. Implementation proposals need GitHub issues.",
}


class ManagementError(ValueError):
    """Management state, evidence or provisioning violates its typed contract."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AuthoredNote(Model):
    model_config = ConfigDict(frozen=True, from_attributes=True, extra="ignore")
    id: int
    author: str
    body: str
    created_at: int


class CompletionEvidence(Model):
    model_config = ConfigDict(frozen=True, from_attributes=True, extra="ignore")
    id: int
    profile: str | None = None
    outcome: str | None = None
    ended_at: int | None = None
    summary: str | None = None
    metadata: dict[str, JsonValue] | None = None


class ArtifactEvidence(Model):
    model_config = ConfigDict(frozen=True, from_attributes=True, extra="ignore")
    id: int
    filename: str
    stored_path: str
    content_type: str | None = None
    size: int | None = None
    uploaded_by: str | None = None
    created_at: int


class TaskView(Model):
    model_config = ConfigDict(frozen=True, from_attributes=True, extra="ignore")
    id: str
    title: str
    body: str | None = Field(default=None, exclude=True)
    assignee: str | None = None
    status: str
    created_by: str | None = None
    priority: int = 0
    result: str | None = None
    handoff_summary: str | None = None
    authored_notes: list[AuthoredNote] = Field(default_factory=list)
    completion_evidence: list[CompletionEvidence] = Field(default_factory=list)
    artifacts: list[ArtifactEvidence] = Field(default_factory=list)
    idempotency_key: str | None = None
    consecutive_failures: int = 0
    last_failure_error: str | None = None


class Cycle(Model):
    parent: str
    children: list[str]
    summary: str
    assignments: dict[Role, str]


class Evidence(Model):
    parent: str
    completed: list[TaskView]
    incomplete: list[TaskView]
    current_work: list[TaskView]
    prior_notes: list[TaskView]


class IncidentRequest(Model):
    incident_id: str = Field(pattern=r"^[A-Z0-9-]{5,80}$")
    severity: Literal["P0", "P1"]
    impact: str = Field(min_length=1, max_length=2000)
    primary_owner: Role
    participants: list[Role] = Field(min_length=2, max_length=6)
    github_links: list[str] = Field(default_factory=list, max_length=12)
    slack_thread: str = ""
    synthetic: bool = False

    @model_validator(mode="after")
    def owner_participates(self) -> "IncidentRequest":
        if self.primary_owner not in self.participants or len(
            set(self.participants)
        ) != len(self.participants):
            raise ManagementError(
                "Primary owner must participate; participants must be unique"
            )
        return self


class Record(Model):
    record_type: Literal["weekly_management", "incident"]
    identity: str
    started_at: str
    status: str = "open"
    primary_owner: str = "chief-of-staff"
    participants: list[str] = Field(default_factory=list)
    severity: str = ""
    impact: str = ""
    current_hypothesis: str = "Unverified"
    current_action: str = "Collect evidence and coordinate handoffs"
    blockers: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    github_links: list[str] = Field(default_factory=list)
    slack_thread: str = ""
    mitigation: str = "Pending"
    resolution: str = "Pending"
    verification: str = "Pending"
    follow_up: list[str] = Field(default_factory=list)
    synthetic: bool = False
    question_plan: str = ""


class IncidentUpdate(Model):
    current_hypothesis: str = "Unverified"
    current_action: str = "Collect evidence"
    blockers: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    github_links: list[str] = Field(default_factory=list)
    slack_thread: str = ""
    mitigation: str = "Pending"
    follow_up: list[str] = Field(default_factory=list)


class Questions(Model):
    """CoS-chosen, evidence-grounded questions for every actual specialist."""

    engineer: str = Field(min_length=10, max_length=2000)
    reviewer: str = Field(min_length=10, max_length=2000)
    qa_security: str = Field(alias="qa-security", min_length=10, max_length=2000)
    sre: str = Field(min_length=10, max_length=2000)
    support: str = Field(min_length=10, max_length=2000)
    growth: str = Field(min_length=10, max_length=2000)

    def for_role(self, role: Role) -> str:
        match role:
            case "engineer":
                return self.engineer
            case "reviewer":
                return self.reviewer
            case "qa-security":
                return self.qa_security
            case "sre":
                return self.sre
            case "support":
                return self.support
            case "growth":
                return self.growth
            case _:
                assert_never(role)


class ManagementRequest(Model):
    action: Literal[
        "weekly_start",
        "team_status",
        "summary_context",
        "incident_start",
        "incident_close",
        "incident_update",
        "weekly_close",
    ]
    week: str = Field(default="", pattern=r"^(?:\d{4}-W\d{2})?$")
    parent_id: str = ""
    questions: Questions | None = None
    incident: IncidentRequest | None = None
    checkpoint: IncidentUpdate | None = None
    resolution: str = Field(default="", max_length=4000)
    verification: str = Field(default="", max_length=4000)
    summary: str = Field(default="", max_length=6000)


class CoordinationRequest(Model):
    intent: str = Field(min_length=1, max_length=5000)
