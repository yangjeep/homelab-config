"""Offline contract and adversarial fixtures; never a live merge claim."""
import base64
import copy
import hashlib
import json
import socket
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'github-broker'))
sys.path.insert(0, str(ROOT / 'authority/merge'))
sys.path.insert(0, str(ROOT / 'authority/policy-observer'))
from merge_models import Policy, Request, Ruleset
from merge_policy import CHECKS, WORKFLOW, Denied, execute
from merge_server import authorize

HEAD = 'a' * 40
BASE = 'b' * 40
MERGED = 'c' * 40


class Fake:
    def __init__(self) -> None:
        self.responses: dict[str, bytes] = {}
        self.writes: list[Request] = []
        self.policy_reads = 0

    def policy(self) -> tuple[Ruleset, ...]:
        self.policy_reads += 1
        return tuple(Ruleset.model_validate_json(self.responses[path]) for path in ('/rulesets/1', '/rulesets/2'))

    def get(self, path: str) -> bytes:
        return self.responses[path]

    def merge(self, request: Request) -> bytes:
        self.writes.append(request)
        data = json.loads(self.responses['/pulls/1'])
        data.update(merged=True, state='closed', merge_commit_sha=MERGED)
        self.responses['/pulls/1'] = json.dumps(data).encode()
        return json.dumps({'merged': True, 'sha': MERGED, 'message': 'merged'}).encode()


@pytest.fixture
def evidence() -> tuple[Fake, Policy, Request]:
    api = Fake()
    repo = {'id': 1, 'full_name': 'yangjeep/leaselab'}
    author = {'id': 10, 'login': 'leaselab-engineer[bot]'}
    data = {
        'number': 1, 'state': 'open', 'draft': False, 'merged': False,
        'mergeable': True, 'mergeable_state': 'clean', 'merge_commit_sha': None,
        'user': author, 'body': 'Closes #779',
        'head': {'sha': HEAD, 'ref': 'feat/test', 'repo': repo},
        'base': {'sha': BASE, 'ref': 'main', 'repo': repo},
    }
    rules = [
        {'type': 'required_status_checks', 'parameters': {
            'required_status_checks': [{'context': name, 'integration_id': app} for name, app in CHECKS.items()],
            'strict_required_status_checks_policy': True}},
        {'type': 'pull_request', 'parameters': {
            'dismiss_stale_reviews_on_push': True, 'required_review_thread_resolution': True}},
        {'type': 'required_deployments', 'parameters': {'required_deployment_environments':
            ['Preview – ops', 'Preview – storefront-alda', 'Preview – leaselab-site']}},
        *[{'type': name} for name in ('deletion', 'non_fast_forward', 'required_linear_history')],
    ]
    quality = {'id': 1, 'enforcement': 'active', 'target': 'branch', 'bypass_actors': [],
               'rules': rules, 'conditions': {'ref_name': {'include': ['refs/heads/main'], 'exclude': []}}}
    actor = copy.deepcopy(quality)
    actor.update(id=2, rules=[{'type': 'update'}], bypass_actors=[{
        'actor_id': 4948588, 'actor_type': 'Integration', 'bypass_mode': 'pull_request'}])
    checks = [{'id': index, 'name': name, 'head_sha': HEAD, 'status': 'completed',
               'conclusion': 'success', 'app': {'id': app}, 'check_suite': {'id': 25},
               'external_id': f'leaselab:v1:pr:1:head:{HEAD}:base:{BASE}',
               'output': {'summary': json.dumps({'pr': 1, 'head': HEAD, 'base': BASE, 'resolved_issues': []})}}
              for index, (name, app) in enumerate(CHECKS.items())]
    run = {'id': 1, 'workflow_id': 211331547, 'path': WORKFLOW, 'head_sha': HEAD,
           'event': 'pull_request', 'status': 'completed', 'conclusion': 'success',
           'check_suite_id': 25, 'run_attempt': 1}
    sources = {
        '/rulesets/1': quality, '/rulesets/2': actor, '/pulls/1': data,
        f'/commits/{HEAD}/check-runs?filter=all&per_page=100': {'total_count': 4, 'check_runs': checks},
        '/pulls/1/reviews?per_page=100': [{'id': 1, 'user': {'id': 11, 'login': 'leaselab-reviewer[bot]'},
                                        'state': 'APPROVED', 'commit_id': HEAD}],
        '/pulls/1/commits?per_page=100': [{'sha': HEAD, 'author': author, 'committer': author}],
        '/issues/779': {'number': 779, 'state': 'open', 'body': 'Contract', 'labels': []},
        '/issues?state=open&per_page=100': [],
        f'/compare/{BASE}...{HEAD}': {'status': 'ahead', 'behind_by': 0,
                                     'merge_base_commit': {'sha': BASE, 'author': author, 'committer': author}},
        f'/actions/workflows/211331547/runs?head_sha={HEAD}&per_page=100': {
            'total_count': 1, 'workflow_runs': [run]},
    }
    for ref in (BASE, HEAD):
        sources[f'/contents/{WORKFLOW}?ref={ref}'] = {'encoding': 'base64', 'path': WORKFLOW,
                                                      'content': base64.b64encode(b'trusted').decode()}
    api.responses = {key: json.dumps(value).encode() for key, value in sources.items()}
    policy = Policy(enabled=True, repository_id=1, quality_ruleset=1, actor_ruleset=2,
                    workflow_sha256=hashlib.sha256(b'trusted').hexdigest())
    return api, policy, Request(pr=1, head=HEAD)


def test_complete_candidate(evidence):
    api, policy, request = evidence
    assert execute(api, request, policy).sha == MERGED
    assert api.writes == [request]


@pytest.mark.parametrize('mutation', ['missing', 'stale', 'wrong_app', 'duplicate', 'failed', 'base'])
def test_qa_denial(evidence, mutation):
    api, policy, request = evidence
    key = f'/commits/{HEAD}/check-runs?filter=all&per_page=100'
    data = json.loads(api.responses[key])
    qa = data['check_runs'][2]
    if mutation == 'missing':
        data['check_runs'].pop(2)
        data['total_count'] -= 1
    if mutation == 'stale':
        qa['head_sha'] = BASE
    if mutation == 'wrong_app':
        qa['app']['id'] = 4948533
    if mutation == 'duplicate':
        data['check_runs'].append(qa)
        data['total_count'] += 1
    if mutation == 'failed':
        qa['conclusion'] = 'failure'
    if mutation == 'base':
        qa['external_id'] = 'old-base'
    api.responses[key] = json.dumps(data).encode()
    with pytest.raises(Denied):
        execute(api, request, policy)
    assert api.writes == []


@pytest.mark.parametrize('path,field,value', [
    ('/pulls/1', 'head', {'sha': BASE, 'ref': 'feat/test', 'repo': {'id': 1, 'full_name': 'yangjeep/leaselab'}}),
    ('/pulls/1', 'user', {'id': 11, 'login': 'leaselab-reviewer[bot]'}),
    ('/pulls/1', 'mergeable', None),
    ('/pulls/1', 'body', 'No contract'),
    ('/rulesets/1', 'bypass_actors', [{'actor_id': 5, 'actor_type': 'RepositoryRole', 'bypass_mode': 'always'}]),
    ('/rulesets/2', 'enforcement', 'disabled'),
])
def test_policy_denial(evidence, path, field, value):
    api, policy, request = evidence
    data = json.loads(api.responses[path])
    data[field] = value
    api.responses[path] = json.dumps(data).encode()
    with pytest.raises(Denied):
        execute(api, request, policy)
    assert not api.writes


def test_security_and_self_review(evidence):
    api, policy, request = evidence
    api.responses['/issues?state=open&per_page=100'] = json.dumps([{
        'number': 2, 'state': 'open', 'body': 'security', 'labels': [{'name': 'P1 bug'}]}]).encode()
    with pytest.raises(Denied):
        execute(api, request, policy)
    assert not api.writes


@pytest.mark.parametrize('raw', [b'null', b'{}', b'{"pr":true,"head":"' + HEAD.encode() + b'"}',
                                b'{"pr":1,"head":"' + HEAD.encode() + b'","role":"reviewer"}'])
def test_request_rejects_malformed(raw):
    with pytest.raises(ValidationError):
        Request.model_validate_json(raw)


def test_malformed_upstream(evidence):
    api, policy, request = evidence
    api.responses['/pulls/1'] = b'[]'
    with pytest.raises(ValidationError):
        execute(api, request, policy)
    assert not api.writes


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Real Linux SO_PEERCRED required')
def test_wrong_uid_socket():
    first, second = socket.socketpair()
    with first, second, pytest.raises(Denied):
        authorize(first, 999999)


@pytest.mark.parametrize('mutation', ['stale_review', 'self_commit', 'wrong_workflow', 'rerun', 'changed_workflow'])
def test_independence_ci_denial(evidence, mutation):
    api, policy, request = evidence
    if mutation == 'stale_review':
        key = '/pulls/1/reviews?per_page=100'
        data = json.loads(api.responses[key])
        data[0]['commit_id'] = BASE
    if mutation == 'self_commit':
        key = '/pulls/1/commits?per_page=100'
        data = json.loads(api.responses[key])
        data[0]['author'] = {'id': 11, 'login': 'leaselab-reviewer[bot]'}
    if mutation in ('wrong_workflow', 'rerun'):
        key = f'/actions/workflows/211331547/runs?head_sha={HEAD}&per_page=100'
        data = json.loads(api.responses[key])
        field = 'workflow_id' if mutation == 'wrong_workflow' else 'run_attempt'
        data['workflow_runs'][0][field] = 2
    if mutation == 'changed_workflow':
        key = f'/contents/{WORKFLOW}?ref={HEAD}'
        data = json.loads(api.responses[key])
        data['content'] = base64.b64encode(b'untrusted').decode()
    api.responses[key] = json.dumps(data).encode()
    with pytest.raises(Denied):
        execute(api, request, policy)
    assert not api.writes


def test_disabled_policy(evidence):
    api, policy, request = evidence
    with pytest.raises(Denied):
        execute(api, request, policy.model_copy(update={'enabled': False}))
    assert not api.writes


@pytest.mark.parametrize('qa_resolved,review_resolved,issue_number,allowed', [
    (True, True, 779, True), (True, False, 779, False),
    (False, True, 779, False), (True, True, 780, False),
])
def test_current_candidate_security_disposition(evidence, qa_resolved, review_resolved, issue_number, allowed):
    api, policy, request = evidence
    key = f'/commits/{HEAD}/check-runs?filter=all&per_page=100'
    checks = json.loads(api.responses[key])
    for index, resolved in ((2, qa_resolved), (3, review_resolved)):
        checks['check_runs'][index]['output']['summary'] = json.dumps({
            'pr': 1, 'head': HEAD, 'base': BASE, 'resolved_issues': [779] if resolved else []})
    api.responses[key] = json.dumps(checks).encode()
    api.responses['/issues?state=open&per_page=100'] = json.dumps([{
        'number': issue_number, 'state': 'open', 'body': 'confirmed bug', 'labels': [{'name': 'P1 bug'}]}]).encode()
    if allowed:
        assert execute(api, request, policy).merged
    else:
        with pytest.raises(Denied):
            execute(api, request, policy)
        assert not api.writes
