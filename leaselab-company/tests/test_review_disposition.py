"""Only exact supervised event sequences can become semantic records."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authority/publisher'))
from publisher_models import Denied
from review_events import disposition
from review_models import Disposition, ReviewIdentity

IDENTITY = ReviewIdentity(provenance='github', pr=759, head='a'*40, base='b'*40, policy='c'*64, source='d'*64, job='e'*64)


def stream(*, identity: ReviewIdentity = IDENTITY, nested: bool = False, failed: bool = False) -> bytes:
    value = Disposition(identity=identity, result='clear', summary='No contradiction found.', findings=())
    checks = dict.fromkeys(('home_canary_denied','auth_open_denied','broker_absent','evidence_absent','nonroot',
                           'secret_env_absent','source_config_absent','source_skills_absent','head_readable','base_readable','network_denied','source_write_denied'), True)
    events = [
        {'type':'thread.started','thread_id':'fixture'}, {'type':'turn.started'},
        {'type':'item.completed','item':{'id':'1','type':'command_execution',
         'command':"/usr/bin/bash -lc 'python3 /opt/review_boundary.py'",'aggregated_output':json.dumps(checks),
         'exit_code':1 if failed else 0,'status':'completed'}},
        {'type':'item.completed','item':{'id':'2','type':'agent_message','text':value.model_dump_json()}},
        {'type':'turn.completed','usage':{'input_tokens':1}}]
    if nested:
        return json.dumps({'type':'item.completed','item':{'id':'fake','type':'command_execution',
            'aggregated_output':'\n'.join(json.dumps(e) for e in events)}}).encode()
    return '\n'.join(json.dumps(e) for e in events).encode()


def test_exact_schema_and_provenance_accepted_as_semantics_only() -> None:
    result = disposition(stream(), IDENTITY, ('docs/sample.md',))
    assert result.family == 'codex'
    assert result.disposition.result == 'clear'
    assert 'approval' not in result.model_dump()


def test_wrong_job_provenance_denied() -> None:
    other = ReviewIdentity(provenance='github', pr=759, head='a'*40, base='b'*40, policy='c'*64, source='d'*64, job='f'*64)
    with pytest.raises(Denied):
        disposition(stream(identity=other), IDENTITY, ('docs/sample.md',))


@pytest.mark.parametrize('raw', [b'PASS', b'{"result":"clear"}', stream(nested=True), stream(failed=True), stream()+b'\n'+stream()])
def test_pass_text_nested_events_failed_boundary_and_duplicates_denied(raw: bytes) -> None:
    with pytest.raises((Denied, ValueError)):
        disposition(raw, IDENTITY, ('docs/sample.md',))


def test_missing_turn_completion_denied() -> None:
    with pytest.raises(Denied):
        disposition(b'\n'.join(stream().splitlines()[:-1]), IDENTITY, ('docs/sample.md',))


def test_extra_disposition_fields_denied() -> None:
    raw = stream().replace(b'No contradiction found.', b'No contradiction found.')
    lines = [json.loads(line) for line in raw.splitlines()]
    value = json.loads(lines[-2]['item']['text'])
    value['approval'] = 'PASS'
    lines[-2]['item']['text'] = json.dumps(value)
    with pytest.raises(ValueError):
        disposition('\n'.join(json.dumps(e) for e in lines).encode(), IDENTITY, ('docs/sample.md',))


@pytest.mark.parametrize('field', ['head','base','policy','source','job'])
def test_each_identity_boundary_is_exact(field: str) -> None:
    data = IDENTITY.model_dump()
    data[field] = 'f' * (40 if field in ('head','base') else 64)
    changed = ReviewIdentity.model_validate(data)
    with pytest.raises(Denied):
        disposition(stream(identity=changed), IDENTITY, ('docs/sample.md',))


@pytest.mark.parametrize('path', ['../secret', 'docs/other.md', '/root/key'])
def test_finding_must_reference_selected_document(path: str) -> None:
    lines = [json.loads(line) for line in stream().splitlines()]
    value = json.loads(lines[-2]['item']['text'])
    value['result'] = 'findings'
    value['findings'] = [{'path':path,'line':1,'kind':'correctness','severity':'P1','explanation':'contradiction',
                          'expected':'3','actual':'30'}]
    lines[-2]['item']['text'] = json.dumps(value)
    with pytest.raises(Denied):
        disposition('\n'.join(json.dumps(e) for e in lines).encode(), IDENTITY, ('docs/sample.md',))

from review_models import Finding


def test_confirmed_security_cannot_be_p2() -> None:
    with pytest.raises(Denied):
        Finding(path='docs/sample.md', line=1, kind='security', severity='P2', explanation='exposed secret', expected='deny', actual='allow')


@pytest.mark.parametrize('severity', ['P0', 'P1'])
def test_security_high_priorities_supported(severity: str) -> None:
    data = {'path':'docs/sample.md','line':1,'kind':'security','severity':severity,
            'explanation':'boundary violation','expected':'deny','actual':'allow'}
    assert Finding.model_validate(data).kind == 'security'
