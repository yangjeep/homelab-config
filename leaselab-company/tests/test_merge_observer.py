"""Offline merge-side observer protocol and fresh policy consumption tests."""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'authority/merge'))
sys.path.insert(0, str(ROOT / 'authority/policy-observer'))
from merge_observer import decode
from merge_policy import Denied

NONCE = 'a' * 64


@pytest.fixture
def packet():
    now = time.time()
    return {'nonce': NONCE, 'repository': 'yangjeep/leaselab',
            'observed_at': datetime.fromtimestamp(now, timezone.utc).isoformat(),
            'rulesets': [{'id': 1, 'name': 'quality', 'source_type': 'Repository',
                         'source': 'yangjeep/leaselab', 'target': 'branch', 'enforcement': 'active',
                         'created_at': '2026-09-15T00:00:00Z', 'updated_at': '2026-09-15T00:00:00Z',
                         'bypass_actors': [], 'rules': [],
                         'conditions': {'ref_name': {'include': ['refs/heads/main'], 'exclude': []}}}]}, now


def test_decodes_when_fresh_nonce_bound_policy(packet):
    # Given: an authenticated observer response generated for this request.
    data, started = packet
    # When: framing and freshness are checked.
    result = decode(json.dumps(data).encode() + b'\n', (NONCE, started))
    # Then: full current policy can be consumed by the existing semantic gate.
    assert len(result) == 1
    assert result[0].id == 1


@pytest.mark.parametrize('field,value', [('nonce', 'b' * 64), ('repository', 'attacker/leaselab'),
    ('observed_at', '2020-01-01T00:00:00+00:00'), ('observed_at', '2099-01-01T00:00:00+00:00'),
    ('observed_at', '2026-09-15T00:00:00'), ('rulesets', [])])
def test_denies_when_response_is_unbound_or_stale(packet, field, value):
    # Given: a replay, wrong repository, invalid clock or empty inventory.
    data, started = packet
    data[field] = value
    # When / Then: no snapshot is returned.
    with pytest.raises((Denied, ValidationError)):
        decode(json.dumps(data).encode() + b'\n', (NONCE, started))


@pytest.mark.parametrize('mutation', ['missing_bypass', 'duplicate', 'missing_repo', 'error',
                                     'no_newline', 'trailing', 'oversize'])
def test_denies_when_snapshot_is_incomplete_or_malformed(packet, mutation):
    # Given: malformed or partial policy evidence.
    data, started = packet
    if mutation == 'missing_bypass':
        del data['rulesets'][0]['bypass_actors']
    if mutation == 'duplicate':
        data['rulesets'].append(data['rulesets'][0])
    if mutation == 'missing_repo':
        del data['repository']
    if mutation == 'error':
        data = {'error': 'policy_unavailable'}
    raw = json.dumps(data).encode() + b'\n'
    if mutation == 'no_newline':
        raw = raw.rstrip(b'\n')
    if mutation == 'trailing':
        raw += b'{}\n'
    if mutation == 'oversize':
        raw = b'x' * 2000001
    # When / Then: partial data is never treated as cached policy.
    with pytest.raises((Denied, ValidationError)):
        decode(raw, (NONCE, started))


def test_final_policy_is_fetched_again_before_merge():
    # Given: a complete offline merge fixture.
    from merge_policy import execute
    from test_merge_gate import evidence
    api, policy, request = evidence.__wrapped__()
    # When: the candidate is merged through the full policy.
    execute(api, request, policy)
    # Then: initial and final gates each request fresh observer evidence.
    assert api.policy_reads == 2


def test_denies_when_final_observation_revokes_actor(monkeypatch):
    # Given: actor authority changes between initial and final policy observations.
    from merge_models import Ruleset
    from merge_policy import execute
    from test_merge_gate import evidence
    api, policy, request = evidence.__wrapped__()
    original = api.policy

    def changing_policy():
        entries = original()
        if api.policy_reads == 2:
            data = json.loads(entries[1].model_dump_json())
            data['bypass_actors'] = []
            return entries[0], Ruleset.model_validate_json(json.dumps(data))
        return entries

    monkeypatch.setattr(api, 'policy', changing_policy)
    # When / Then: a fresh final check denies before any merge write.
    with pytest.raises(Denied):
        execute(api, request, policy)
    assert api.policy_reads == 2
    assert api.writes == []
