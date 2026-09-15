"""Strict job identities and state invariants, independent of caller assertions."""
import json
from typing import Annotated, ClassVar, Literal, Self, assert_never

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

Sha = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{40}$')]
Digest = Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')]
Positive = Annotated[int, Field(gt=0)]
Role = Literal['qa-security', 'reviewer']
State = Literal['queued', 'running', 'passed', 'failed', 'blocked', 'stale']


class Denied(Exception):
    """Untrusted input, malformed storage or invalid state transition."""


class Record(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, strict=True, extra='forbid')


class Request(Record):
    pr: Annotated[int, Field(gt=0, le=2147483647)]
    head: Sha


class Candidate(Request):
    """Fresh repository observation supplied only by the future trusted supervisor."""
    repository: Literal['yangjeep/leaselab'] = 'yangjeep/leaselab'
    base: Sha


class Identity(Candidate):
    role: Role
    policy_version: Literal[1] = 1


class Completion(Record):
    """Future supervisor-owned result; never accepted by the request parser."""
    state: Literal['passed', 'failed', 'blocked']
    evidence_digest: Digest


class Manifest(Record):
    job_id: Digest
    identity: Identity
    state: State
    created_ns: Positive
    started_ns: Positive | None = None
    finished_ns: Positive | None = None
    evidence_digest: Digest | None = None

    @model_validator(mode='after')
    def coherent(self) -> Self:
        match self.state:
            case 'queued':
                valid = self.started_ns is None and self.finished_ns is None and self.evidence_digest is None
            case 'running':
                valid = self.started_ns is not None and self.finished_ns is None and self.evidence_digest is None
            case 'stale':
                valid = self.finished_ns is not None and self.evidence_digest is None
            case 'passed' | 'failed' | 'blocked':
                valid = self.started_ns is not None and self.finished_ns is not None and self.evidence_digest is not None
            case unreachable:
                assert_never(unreachable)
        if not valid:
            raise Denied
        return self


class Pointer(Record):
    job_id: Digest


def unique_keys(pairs: list[tuple[str, JsonValue]]) -> None:
    names = [name for name, _value in pairs]
    if len(set(names)) != len(names):
        raise Denied


def parse_request(raw: bytes) -> Request:
    if len(raw) > 256:
        raise Denied
    request = Request.model_validate_json(raw)
    json.loads(raw, object_pairs_hook=unique_keys)
    return request
