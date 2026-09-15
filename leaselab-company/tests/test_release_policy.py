"""Offline release security-boundary fixtures, not production deployment evidence."""
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from authority.release.release_models import Evidence, Peer, Policy, Request
from authority.release.release_policy import Denied, evaluate


@pytest.fixture
def fixture() -> tuple[Request, Evidence, tuple[Peer, Policy]]:
    candidate = {'repository': 'yangjeep/leaselab', 'repository_id': 1, 'pr': 12,
                     'head': 'a' * 40, 'base': 'b' * 40, 'merged_sha': 'c' * 40,
                     'build_id': 'build-1', 'build_sha256': 'd' * 64, 'environment': 'production'}
    migration = {'identifier': '0040_example.sql', 'sha256': 'e' * 64, 'change': 'added',
                     'semantics': 'reviewed-reversible-additive', 'rollback_sha256': 'f' * 64,
                     'rollback_tested': True}
    qa = {'candidate': candidate, 'publisher_id': 4948555, 'success': True}
    review = {'candidate': candidate, 'publisher_id': 4948588, 'success': True,
                  'migrations': [migration], 'inventory_complete': True}
    ci = {'candidate': candidate, 'publisher_id': 15368, 'success': True}
    evidence = {'candidate': candidate, 'merged_by': 'leaselab-reviewer[bot]', 'merged': True,
                    'main_sha': 'c' * 40, 'prod_sha': 'b' * 40, 'fast_forward': True,
                    'qa': qa, 'review': review, 'ci': ci, 'ci_workflow_sha256': '1' * 64,
                    'ci_run_id': 12, 'ci_run_attempt': 1, 'build_available': True,
                    'build_source_sha': 'c' * 40, 'migrations': [migration], 'inventory_complete': True,
                    'rollback_sha': 'b' * 40, 'rollback_tested': True, 'blockers_clear': True}
    request = Request.model_validate_json(json.dumps({'candidate': candidate, 'migrations': ['0040_example.sql']}))
    return request, Evidence.model_validate_json(json.dumps(evidence)), (
        Peer(uid=1005), Policy(sre_uid=1005, repository_id=1, ci_workflow_sha256='1' * 64))


def test_eligible_when_exact_trusted_evidence_matches(fixture):
    # Given: immutable approved release and authenticated SRE peer.
    request, evidence, authority = fixture
    # When: eligibility is evaluated without any transport.
    result = evaluate(request, evidence, authority)
    # Then: the decision retains exact artifact identities and prod precondition.
    assert result.candidate == request.candidate
    assert result.migrations == evidence.migrations
    assert result.expected_prod_sha == evidence.prod_sha


@pytest.mark.parametrize('path,value', [
    ('merged', False), ('main_sha', 'a' * 40), ('fast_forward', False),
    ('qa.publisher_id', 4948533), ('qa.success', False), ('qa.candidate.head', 'b' * 40),
    ('review.publisher_id', 4948533), ('review.success', False),
    ('review.candidate.base', 'c' * 40), ('review.inventory_complete', False),
    ('ci.publisher_id', 4948533), ('ci.success', False),
    ('ci.candidate.merged_sha', 'a' * 40), ('ci_run_attempt', 2),
    ('ci_workflow_sha256', '2' * 64), ('build_source_sha', 'a' * 40),
    ('build_available', False), ('candidate.build_id', 'other-build'),
    ('inventory_complete', False), ('rollback_sha', None),
    ('rollback_tested', False), ('blockers_clear', False),
])
def test_denied_when_release_binding_changes(fixture, path, value):
    # Given: one invalid trusted fact.
    request, evidence, authority = fixture
    data = json.loads(evidence.model_dump_json())
    target = data
    parts = path.split('.')
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    altered = Evidence.model_validate_json(json.dumps(data))
    # When / Then: no eligibility is issued.
    with pytest.raises(Denied):
        evaluate(request, altered, authority)


@pytest.mark.parametrize('field,value', [
    ('change', 'deleted'), ('change', 'modified'), ('change', 'unknown'),
    ('semantics', 'destructive'), ('semantics', 'irreversible'), ('semantics', 'unknown'),
    ('rollback_sha256', None), ('rollback_tested', False), ('sha256', '0' * 64),
])
def test_denied_when_migration_is_unsafe_or_unreviewed(fixture, field, value):
    # Given: an unsafe or changed migration artifact.
    request, evidence, authority = fixture
    data = json.loads(evidence.model_dump_json())
    data['migrations'][0][field] = value
    # Also alter review to ensure unsafe semantics remain denied even when reviewed.
    if field != 'sha256':
        data['review']['migrations'][0][field] = value
    altered = Evidence.model_validate_json(json.dumps(data))
    # When / Then: the policy refuses the artifact.
    with pytest.raises(Denied):
        evaluate(request, altered, authority)


@pytest.mark.parametrize('field,value', [('sql', 'SELECT 1'), ('command', 'true'),
                                         ('role', 'sre'), ('migrations', ['../escape.sql'])])
def test_rejects_when_request_contains_arbitrary_input(fixture, field, value):
    # Given: caller-supplied execution or role data.
    request, _, _ = fixture
    data = json.loads(request.model_dump_json())
    data[field] = value
    # When / Then: parsing rejects it before policy evaluation.
    with pytest.raises(ValidationError):
        Request.model_validate_json(json.dumps(data))


def test_denied_when_peer_is_not_sre(fixture):
    # Given: an authenticated different OS user.
    request, evidence, (_, policy) = fixture
    # When / Then: request claims cannot grant SRE authority.
    with pytest.raises(Denied):
        evaluate(request, evidence, (Peer(uid=1001), policy))


@pytest.mark.parametrize('migrations', [[], ['0041_unknown.sql'], ['0040_example.sql', '0040_example.sql']])
def test_denied_when_requested_inventory_differs(fixture, migrations):
    # Given: missing, unapproved, or duplicate migration identifiers.
    request, evidence, authority = fixture
    data = json.loads(request.model_dump_json())
    data['migrations'] = migrations
    altered = Request.model_validate_json(json.dumps(data))
    # When / Then: complete reviewed ordering is required.
    with pytest.raises(Denied):
        evaluate(altered, evidence, authority)


@pytest.mark.parametrize('field,value', [('repository', 'attacker/leaselab'), ('environment', 'preview'),
                                         ('merged_sha', 'main')])
def test_rejects_when_candidate_scope_is_invalid(fixture, field, value):
    # Given: a mutable ref or out-of-scope target.
    request, _, _ = fixture
    data = json.loads(request.model_dump_json())
    data['candidate'][field] = value
    # When / Then: the strict boundary rejects it.
    with pytest.raises(ValidationError):
        Request.model_validate_json(json.dumps(data))


def test_eligible_when_reviewed_inventory_is_empty(fixture):
    # Given: a release with authenticated evidence of no migrations.
    request, evidence, authority = fixture
    request_data = json.loads(request.model_dump_json())
    evidence_data = json.loads(evidence.model_dump_json())
    request_data['migrations'] = []
    evidence_data['migrations'] = []
    evidence_data['review']['migrations'] = []
    # When: the complete empty inventory is evaluated.
    result = evaluate(Request.model_validate_json(json.dumps(request_data)),
                      Evidence.model_validate_json(json.dumps(evidence_data)), authority)
    # Then: promotion eligibility contains no migration operations.
    assert result.migrations == ()
