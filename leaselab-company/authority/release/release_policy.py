"""Deterministic release eligibility over trusted evidence; no I/O or execution."""
from .release_models import Eligible, Evidence, Peer, Policy, Request


class Denied(Exception):
    """Trusted evidence does not establish release eligibility; escalate."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Denied(reason)


def evaluate(request: Request, evidence: Evidence, authority: tuple[Peer, Policy]) -> Eligible:
    peer, policy = authority
    candidate = evidence.candidate
    require(peer.uid == policy.sre_uid, 'authenticated peer is not SRE')
    require(candidate.repository_id == policy.repository_id, 'repository identity mismatch')
    require(request.candidate == candidate, 'unapproved release candidate')
    require(evidence.merged and evidence.main_sha == candidate.merged_sha, 'not current merged main')
    require(candidate.merged_sha not in (candidate.head, candidate.base), 'missing merge identity')
    require(evidence.fast_forward, 'prod cannot fast-forward')
    require(evidence.prod_sha != candidate.merged_sha, 'candidate already promoted')
    for attestation, publisher in ((evidence.qa, 4948555), (evidence.review, 4948588), (evidence.ci, 15368)):
        require(attestation.publisher_id == publisher, 'untrusted attestation publisher')
        require(attestation.success and attestation.candidate == candidate, 'stale or failed attestation')
    require(evidence.ci_workflow_sha256 == policy.ci_workflow_sha256, 'unapproved CI workflow')
    require(evidence.ci_run_attempt == 1, 'ambiguous CI retry')
    require(evidence.build_available and evidence.build_source_sha == candidate.merged_sha,
            'build missing or not bound to merged SHA')
    require(evidence.blockers_clear, 'unresolved release blockers')
    require(evidence.rollback_tested and evidence.rollback_sha == evidence.prod_sha,
            'missing tested rollback to current prod')
    require(evidence.inventory_complete and evidence.review.inventory_complete, 'incomplete migration inventory')
    require(evidence.migrations == evidence.review.migrations, 'migration artifacts differ from review')
    identifiers = tuple(migration.identifier for migration in evidence.migrations)
    require(request.migrations == identifiers, 'requested migration inventory differs from approved inventory')
    require(len(identifiers) == len(set(identifiers)), 'duplicate migration')
    for migration in evidence.migrations:
        # Semantics are a trusted reviewer contract, never a keyword scan of SQL.
        require(migration.change == 'added', 'existing, deleted, or unknown migration change')
        require(migration.semantics == 'reviewed-reversible-additive', 'unsupported migration semantics; escalate')
        require(migration.rollback_sha256 is not None and migration.rollback_tested,
                'missing reviewed and tested migration rollback')
    return Eligible(candidate=candidate, migrations=evidence.migrations, expected_prod_sha=evidence.prod_sha)
