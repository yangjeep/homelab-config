"""Strict boundary models for merge authority input and GitHub evidence."""
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Sha = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{40}$')]


class Evidence(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True)


class Request(Evidence):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True, extra='forbid')
    pr: Annotated[int, Field(gt=0, le=2147483647)]
    head: Sha


class Identity(Evidence):
    id: int
    login: str


class Repository(Evidence):
    id: int
    full_name: str


class Ref(Evidence):
    sha: Sha
    ref: str
    repo: Repository


class Pull(Evidence):
    number: int
    state: str
    draft: bool
    merged: bool
    mergeable: bool | None
    mergeable_state: str
    merge_commit_sha: Sha | None
    user: Identity
    head: Ref
    base: Ref
    body: str | None


class App(Evidence):
    id: int


class CheckOutput(Evidence):
    summary: str | None


class Disposition(Evidence):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True, extra='forbid')
    pr: Annotated[int, Field(gt=0)]
    head: Sha
    base: Sha
    resolved_issues: list[Annotated[int, Field(gt=0)]]


class Check(Evidence):
    id: int
    name: str
    head_sha: Sha
    status: str
    conclusion: str | None
    app: App
    external_id: str | None
    output: CheckOutput
    check_suite: App


class Checks(Evidence):
    total_count: int
    check_runs: list[Check]


class Review(Evidence):
    id: int
    user: Identity
    state: str
    commit_id: Sha


class Label(Evidence):
    name: str


class Issue(Evidence):
    number: int
    state: str
    labels: list[Label]
    body: str | None


class Commit(Evidence):
    sha: Sha
    author: Identity | None
    committer: Identity | None


class Comparison(Evidence):
    status: str
    behind_by: int
    merge_base_commit: Commit


class RequiredCheck(Evidence):
    context: str
    integration_id: int


class Parameters(Evidence):
    required_status_checks: list[RequiredCheck] = []
    strict_required_status_checks_policy: bool = False
    required_deployment_environments: list[str] = []
    dismiss_stale_reviews_on_push: bool = False
    required_review_thread_resolution: bool = False


class Rule(Evidence):
    type: str
    parameters: Parameters = Parameters()


class Actor(Evidence):
    actor_id: int
    actor_type: str
    bypass_mode: str


class RefCondition(Evidence):
    include: list[str]
    exclude: list[str]


class Conditions(Evidence):
    ref_name: RefCondition


class Ruleset(Evidence):
    id: int
    enforcement: str
    target: str
    bypass_actors: list[Actor]
    rules: list[Rule]
    conditions: Conditions


class WorkflowRun(Evidence):
    id: int
    workflow_id: int
    head_sha: Sha
    event: str
    status: str
    conclusion: str | None
    check_suite_id: int
    path: str
    run_attempt: int


class Runs(Evidence):
    total_count: int
    workflow_runs: list[WorkflowRun]


class File(Evidence):
    encoding: Literal['base64']
    content: str
    path: str


class MergeResult(Evidence):
    merged: bool
    sha: Sha
    message: str


class Policy(Evidence):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True, extra='forbid')
    enabled: bool = False
    repository_id: int
    quality_ruleset: int
    actor_ruleset: int
    workflow_sha256: Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
