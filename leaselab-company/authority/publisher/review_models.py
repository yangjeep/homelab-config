"""Strict independent disposition; semantic findings remain separate from approval."""
from typing import Annotated, Literal, Self

from publisher_models import Denied, Digest, Record, Sha
from pydantic import Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(min_length=1, max_length=1200)]


class ReviewIdentity(Record):
    repository: Literal['yangjeep/leaselab'] = 'yangjeep/leaselab'
    provenance: Literal['github', 'synthetic-fixture']
    pr: Annotated[int, Field(gt=0)]
    head: Sha
    base: Sha
    policy: Digest
    source: Digest
    job: Digest


class Finding(Record):
    path: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    line: Annotated[int, Field(gt=0, le=100000)]
    kind: Literal['security', 'correctness']
    severity: Literal['P0', 'P1', 'P2']
    explanation: Text
    expected: Text
    actual: Text


    @model_validator(mode='after')
    def security_priority(self) -> Self:
        if self.kind == 'security' and self.severity == 'P2':
            raise Denied
        return self


class Disposition(Record):
    identity: ReviewIdentity
    result: Literal['clear', 'findings', 'inconclusive']
    summary: Text
    findings: Annotated[tuple[Finding, ...], Field(max_length=20)]

    @model_validator(mode='after')
    def coherent(self) -> Self:
        if (self.result == 'clear' and self.findings) or (self.result == 'findings' and not self.findings):
            raise Denied
        return self
