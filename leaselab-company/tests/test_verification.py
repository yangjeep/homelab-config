"""Recipe boundaries and exact repository observations."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authority/publisher'))
from publisher_models import Denied
from source_models import Entry, Tree, git_hash
from verification_observe import candidate
from verification_recipe import changes, check_document


def tree(content: bytes, directory: str = 'docs') -> Tree:
    blob = git_hash('blob', content)
    subtree = git_hash('tree', b'100644 sample.md\0' + bytes.fromhex(blob))
    root = git_hash('tree', b'40000 ' + directory.encode() + b'\0' + bytes.fromhex(subtree))
    return Tree(sha=root, truncated=False, tree=(Entry(path=directory, mode='040000', type='tree', sha=subtree),
                Entry(path=directory + '/sample.md', mode='100644', type='blob', sha=blob, size=len(content))))


def test_docs_recipe_selects_only_changed_markdown() -> None:
    assert changes(tree(b'new\n'), tree(b'old\n')) == ('docs/sample.md',)


def test_application_change_cannot_select_docs_recipe() -> None:
    with pytest.raises(Denied):
        changes(tree(b'new\n', 'apps'), tree(b'old\n', 'apps'))


def test_empty_change_is_not_success() -> None:
    with pytest.raises(Denied):
        changes(tree(b'same\n'), tree(b'same\n'))


@pytest.mark.parametrize('content', [b'', b'bad\0\n', b'no newline', b'<<<<<<< seeded defect\n', b'\xff\n'])
def test_seeded_doc_defect_fails(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / 'doc.md'
    path.write_bytes(content)
    with pytest.raises((Denied, UnicodeError)):
        check_document(path)


def test_safe_document_runs(tmp_path: Path) -> None:
    path = tmp_path / 'doc.md'
    path.write_text('# Example\n')
    check_document(path)


@pytest.mark.parametrize('field', ['ref', 'repo'])
def test_pr_observation_rejects_wrong_identity(field: str) -> None:
    value = {'number': 759, 'head': {'sha': 'a' * 40, 'ref': 'feature', 'repo': {'full_name': 'yangjeep/leaselab'}},
             'base': {'sha': 'b' * 40, 'ref': 'main', 'repo': {'full_name': 'yangjeep/leaselab'}}}
    if field == 'sha':
        value['head']['sha'] = 'c' * 40
    elif field == 'ref':
        value['base']['ref'] = 'production'
    else:
        value['head']['repo'] = {'full_name': 'attacker/fork'}
    with pytest.raises((Denied, ValueError)):
        candidate(json.dumps(value).encode(), json.dumps({'pr':759,'head':'a'*40}).encode())

from executor_capture import Capture
from publisher_files import Files
from publisher_jobs import Jobs
from publisher_models import Candidate, Request
import verification_run


@pytest.mark.parametrize('mode,expected', [('success', 'blocked'), ('test-failure', 'failed'), ('supervisor-error', 'failed'), ('stale', 'stale')])
def test_completion_never_authorizes_and_records_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, expected: str) -> None:
    store = tmp_path / 'jobs'
    store.mkdir(mode=0o700)
    evidence = tmp_path / 'evidence'
    evidence.mkdir(mode=0o700)
    code = tmp_path / 'code'
    code.mkdir()
    (code / 'verification_test.py').write_text('trusted runner')
    monkeypatch.setattr(verification_run, 'CODE', code)
    monkeypatch.setattr(verification_run, 'policy_digest', lambda: 'd' * 64)
    initial = Candidate(pr=759, head='a' * 40, base='b' * 40)
    with Files(store) as files:
        jobs = Jobs(files, 'qa-security')
        manifest = jobs.begin(Request(pr=759, head='a' * 40), initial)
        jobs.start(manifest.job_id, initial)
        current = Candidate(pr=759, head='c' * 40, base='b' * 40) if mode == 'stale' else initial
        result = Capture(exit_code=1 if mode == 'test-failure' else 0, digest='e' * 64, size=5, limited=False)
        with pytest.raises(SystemExit):
            verification_run.finish(jobs, manifest.job_id, current, evidence, result, error=mode == 'supervisor-error')
        assert jobs.load(manifest.job_id).state == expected
        assert not jobs.eligible(manifest.job_id, initial)
        assert (evidence / 'verification.json').stat().st_mode & 0o777 == 0o400

import executor_config


@pytest.mark.parametrize('interrupted', [False, True])
def test_supervisor_error_and_interrupted_retry_finalize_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupted: bool) -> None:
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'evidence').mkdir()
    executors = tmp_path / 'executors'
    (executors / 'qa-security').mkdir(parents=True)
    (executors / 'qa-security/lock').touch()
    code = tmp_path / 'code'
    code.mkdir()
    (code / 'verification_test.py').write_text('fixed')
    monkeypatch.setattr(executor_config, 'ROOT', executors)
    monkeypatch.setattr(verification_run, 'ROOT', runtime)
    monkeypatch.setattr(verification_run, 'CODE', code)
    monkeypatch.setattr(verification_run, 'policy_digest', lambda: 'd' * 64)
    initial = Candidate(pr=759, head='a' * 40, base='b' * 40)
    monkeypatch.setattr(verification_run, 'observe', lambda _raw, _output: initial)
    def failed_materialize(_candidate: Candidate, _path: Path) -> Path:
        raise Denied
    monkeypatch.setattr(verification_run, 'materialize', failed_materialize)
    store = runtime / 'verification-stores' / ('d' * 64)
    if interrupted:
        store.mkdir(parents=True, mode=0o700)
        with Files(store) as files:
            jobs = Jobs(files, 'qa-security')
            old = jobs.begin(Request(pr=759, head='a' * 40), initial)
            jobs.start(old.job_id, initial)
    with pytest.raises(SystemExit) as error:
        verification_run.run(json.dumps({'pr':759,'head':'a'*40}))
    assert error.value.code == 2
    with Files(store) as files:
        jobs = Jobs(files, 'qa-security')
        current = jobs.current(759)
        assert current is not None
        assert jobs.load(current).state == 'failed'
    assert len(list((runtime / 'evidence').glob('*/verification.json'))) == 1
