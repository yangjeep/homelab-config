"""Atomic local lifecycle only: no execution, network, credentials or publication."""
import hashlib
import time
from typing import Final

from publisher_files import Files
from publisher_models import (
    Candidate,
    Completion,
    Denied,
    Identity,
    Manifest,
    Pointer,
    Request,
    Role,
)

TERMINAL: Final = frozenset({'passed', 'failed', 'blocked', 'stale'})


def identifier(identity: Identity) -> str:
    return hashlib.sha256(identity.model_dump_json().encode()).hexdigest()


def matches(manifest: Manifest, candidate: Candidate) -> bool:
    value = manifest.identity
    return (value.pr, value.head, value.base, value.repository) == (
        candidate.pr, candidate.head, candidate.base, candidate.repository)


class Jobs:
    """Fixed-role service store; callers can submit only parsed Request values."""
    def __init__(self, files: Files, role: Role) -> None:
        self.files: Files = files
        self.role: Role = role

    def load(self, job_id: str) -> Manifest:
        blob = self.files.read(job_id + '.json')
        if blob is None:
            raise Denied
        manifest = Manifest.model_validate_json(blob.payload)
        if (manifest.job_id != job_id or identifier(manifest.identity) != job_id
                or manifest.identity.role != self.role or blob.final != (manifest.state in TERMINAL)):
            raise Denied
        return manifest

    def current(self, pr: int) -> str | None:
        blob = self.files.read(f'current-{pr}.json')
        if blob is None:
            return None
        if blob.final:
            raise Denied
        return Pointer.model_validate_json(blob.payload).job_id

    def _save(self, manifest: Manifest) -> Manifest:
        self.files.write(manifest.job_id + '.json', manifest.model_dump_json().encode(),
                         final=manifest.state in TERMINAL)
        return manifest

    def _stale(self, manifest: Manifest) -> Manifest:
        if manifest.state in TERMINAL:
            return manifest
        return self._save(Manifest(job_id=manifest.job_id, identity=manifest.identity,
                                  created_ns=manifest.created_ns, started_ns=manifest.started_ns,
                                  state='stale', finished_ns=time.time_ns()))

    def begin(self, request: Request, candidate: Candidate) -> Manifest:
        if request.pr != candidate.pr or request.head != candidate.head:
            raise Denied
        identity = Identity(pr=candidate.pr, head=candidate.head, base=candidate.base,
                            repository=candidate.repository, role=self.role)
        job_id = identifier(identity)
        with self.files.lock():
            previous = self.current(request.pr)
            if previous is not None and previous != job_id:
                old = self.load(previous)
                if old.identity.pr != request.pr:
                    raise Denied
                _ = self._stale(old)
            blob = self.files.read(job_id + '.json')
            if blob is None:
                result = self._save(Manifest(job_id=job_id, identity=identity, state='queued',
                                            created_ns=time.time_ns()))
            else:
                result = self.load(job_id)
            self.files.write(f'current-{request.pr}.json', Pointer(job_id=job_id).model_dump_json().encode())
            return result

    def start(self, job_id: str, candidate: Candidate) -> Manifest:
        with self.files.lock():
            manifest = self.load(job_id)
            if manifest.state in TERMINAL:
                raise Denied
            if not matches(manifest, candidate) or self.current(candidate.pr) != job_id:
                return self._stale(manifest)
            if manifest.state == 'running':
                return manifest
            return self._save(Manifest(job_id=manifest.job_id, identity=manifest.identity,
                                      created_ns=manifest.created_ns, state='running',
                                      started_ns=time.time_ns()))

    def complete(self, job_id: str, candidate: Candidate, completion: Completion) -> Manifest:
        with self.files.lock():
            manifest = self.load(job_id)
            if manifest.state != 'running':
                raise Denied
            if not matches(manifest, candidate) or self.current(candidate.pr) != job_id:
                return self._stale(manifest)
            return self._save(Manifest(job_id=manifest.job_id, identity=manifest.identity,
                                      created_ns=manifest.created_ns, started_ns=manifest.started_ns,
                                      state=completion.state, finished_ns=time.time_ns(),
                                      evidence_digest=completion.evidence_digest))

    def eligible(self, job_id: str, candidate: Candidate) -> bool:
        """An old immutable PASS is never authorization for a different observation."""
        with self.files.lock():
            manifest = self.load(job_id)
            return (manifest.state == 'passed' and matches(manifest, candidate)
                    and self.current(candidate.pr) == job_id)
