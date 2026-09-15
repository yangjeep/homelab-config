"""Release boundary contracts; evidence must originate in trusted controller adapters."""
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Sha = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{40}$')]
Digest = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
Identifier = Annotated[str, StringConstraints(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$')]
MigrationId = Annotated[str, StringConstraints(pattern=r'^[0-9]{4}_[a-z0-9_]+\.sql$')]
Positive = Annotated[int, Field(gt=0)]


class Contract(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True, extra='forbid')


class Candidate(Contract):
    repository: Literal['yangjeep/leaselab']
    repository_id: Positive
    pr: Positive
    head: Sha
    base: Sha
    merged_sha: Sha
    build_id: Identifier
    build_sha256: Digest
    environment: Literal['production']


class Request(Contract):
    candidate: Candidate
    migrations: tuple[MigrationId, ...]


class Peer(Contract):
    """OS-authenticated peer, supplied separately from the request body."""
    uid: Positive


class Policy(Contract):
    sre_uid: Positive
    repository_id: Positive
    ci_workflow_sha256: Digest


class Attestation(Contract):
    candidate: Candidate
    publisher_id: Positive
    success: bool


class Migration(Contract):
    identifier: MigrationId
    sha256: Digest
    change: Literal['added', 'modified', 'deleted', 'unknown']
    semantics: Literal['reviewed-reversible-additive', 'destructive', 'irreversible', 'unknown']
    rollback_sha256: Digest | None
    rollback_tested: bool


class MigrationReview(Attestation):
    migrations: tuple[Migration, ...]
    inventory_complete: bool


class Evidence(Contract):
    """Not caller assertions: adapter-authenticated, immutable snapshot of source facts."""
    candidate: Candidate
    merged_by: Literal['leaselab-reviewer[bot]']
    merged: bool
    main_sha: Sha
    prod_sha: Sha
    fast_forward: bool
    qa: Attestation
    review: MigrationReview
    ci: Attestation
    ci_workflow_sha256: Digest
    ci_run_id: Positive
    ci_run_attempt: Positive
    build_available: bool
    build_source_sha: Sha
    migrations: tuple[Migration, ...]
    inventory_complete: bool
    rollback_sha: Sha | None
    rollback_tested: bool
    blockers_clear: bool


class Eligible(Contract):
    """Eligibility only; never a deployment receipt or reusable authorization token."""
    candidate: Candidate
    migrations: tuple[Migration, ...]
    expected_prod_sha: Sha
