"""Publisher job storage boundary tests; no network or privileged credential use."""
import json
import os
from pathlib import Path
import stat
import sys

import pytest
from pydantic import ValidationError

SOURCE = Path(__file__).resolve().parents[1] / 'authority/publisher'
sys.path.insert(0, str(SOURCE))
from publisher_files import Files
from publisher_jobs import Jobs
from publisher_models import Candidate, Completion, Denied, Request, parse_request

HEAD = 'a' * 40
BASE = 'b' * 40
CANDIDATE = Candidate(pr=1, head=HEAD, base=BASE)
REQUEST = Request(pr=1, head=HEAD)
PASS = Completion(state='passed', evidence_digest='e' * 64)


@pytest.fixture
def root(tmp_path):
    path = tmp_path / 'qa'
    path.mkdir(mode=0o700)
    return path.resolve()


@pytest.mark.parametrize('field', ['PASS', 'pass', 'state', 'result', 'path', 'command', 'role', 'base', 'repository', 'evidence_digest'])
def test_caller_cannot_supply_authority(field):
    raw = json.dumps({'pr': 1, 'head': HEAD, field: 'forged'}).encode()
    with pytest.raises((Denied, ValidationError)):
        parse_request(raw)


@pytest.mark.parametrize('raw', [b'null', b'[]', b'{}', b'x' * 257,
    b'{"pr":true,"head":"' + HEAD.encode() + b'"}',
    b'{"pr":1,"pr":2,"head":"' + HEAD.encode() + b'"}',
    b'{"pr":1,"head":"../not-a-sha"}',
    b'{"pr":1,"head":"' + HEAD.encode() + b'"} trailing'])
def test_malformed_request(raw):
    with pytest.raises((Denied, ValidationError)):
        parse_request(raw)


def test_dedupe_restart_immutable_completion(root):
    assert parse_request(REQUEST.model_dump_json().encode()) == REQUEST
    with Files(root) as files:
        jobs = Jobs(files, 'qa-security')
        first = jobs.begin(REQUEST, CANDIDATE)
        assert jobs.begin(REQUEST, CANDIDATE) == first
        assert jobs.start(first.job_id, CANDIDATE).state == 'running'
        assert jobs.start(first.job_id, CANDIDATE).state == 'running'
        complete = jobs.complete(first.job_id, CANDIDATE, PASS)
        assert jobs.eligible(first.job_id, CANDIDATE)
        assert stat.S_IMODE((root / (first.job_id + '.json')).stat().st_mode) == 0o400
        with pytest.raises(Denied):
            jobs.complete(first.job_id, CANDIDATE, PASS)
        with pytest.raises(Denied):
            files.write(first.job_id + '.json', b'{}')
    with Files(root) as reopened:
        assert Jobs(reopened, 'qa-security').begin(REQUEST, CANDIDATE) == complete


@pytest.mark.parametrize('field', ['head', 'base'])
def test_new_candidate_stales_running_job(root, field):
    with Files(root) as files:
        jobs = Jobs(files, 'qa-security')
        old = jobs.begin(REQUEST, CANDIDATE)
        jobs.start(old.job_id, CANDIDATE)
        fresh = CANDIDATE.model_copy(update={field: 'c' * 40})
        new = jobs.begin(Request(pr=1, head=fresh.head), fresh)
        assert new.job_id != old.job_id and new.state == 'queued'
        assert jobs.load(old.job_id).state == 'stale'
        assert not jobs.eligible(old.job_id, fresh)
        with pytest.raises(Denied):
            jobs.complete(old.job_id, CANDIDATE, PASS)


def test_completed_manifest_preserved_after_head_moves(root):
    with Files(root) as files:
        jobs = Jobs(files, 'qa-security')
        old = jobs.begin(REQUEST, CANDIDATE)
        jobs.start(old.job_id, CANDIDATE)
        jobs.complete(old.job_id, CANDIDATE, PASS)
        path = root / (old.job_id + '.json')
        before = path.read_bytes()
        fresh = Candidate(pr=1, head='c' * 40, base=BASE)
        jobs.begin(Request(pr=1, head=fresh.head), fresh)
        assert path.read_bytes() == before
        assert not jobs.eligible(old.job_id, fresh)
        assert not jobs.eligible(old.job_id, CANDIDATE)


def test_fresh_observation_rejects_stale_request_and_completion(root):
    with Files(root) as files:
        jobs = Jobs(files, 'qa-security')
        fresh = Candidate(pr=1, head='c' * 40, base=BASE)
        with pytest.raises(Denied):
            jobs.begin(REQUEST, fresh)
        old = jobs.begin(REQUEST, CANDIDATE)
        jobs.start(old.job_id, CANDIDATE)
        assert jobs.complete(old.job_id, fresh, PASS).state == 'stale'


def test_no_completion_before_execution(root):
    with Files(root) as files:
        jobs = Jobs(files, 'qa-security')
        job = jobs.begin(REQUEST, CANDIDATE)
        with pytest.raises(Denied):
            jobs.complete(job.job_id, CANDIDATE, PASS)
        assert not jobs.eligible(job.job_id, CANDIDATE)


def test_role_bound_identity(root):
    with Files(root) as files:
        job = Jobs(files, 'qa-security').begin(REQUEST, CANDIDATE)
        with pytest.raises(Denied):
            Jobs(files, 'reviewer').load(job.job_id)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'fifo', 'oversize', 'permissions'])
def test_storage_object_rejection(root, kind):
    path = root / 'current-1.json'
    if kind == 'symlink':
        path.symlink_to('/etc/passwd')
    if kind == 'hardlink':
        source = root / 'other'
        source.write_bytes(b'{}')
        source.chmod(0o600)
        os.link(source, path)
    if kind == 'fifo':
        os.mkfifo(path, 0o600)
    if kind == 'oversize':
        path.write_bytes(b'x' * 16385)
        path.chmod(0o600)
    if kind == 'permissions':
        path.write_bytes(b'{}')
        path.chmod(0o666)
    with Files(root) as files, pytest.raises((Denied, OSError)):
        files.read('current-1.json')


def test_path_traversal_and_root_symlink(root):
    with Files(root) as files, pytest.raises(Denied):
        files.read('../outside')
    alias = root.parent / 'alias'
    alias.symlink_to(root)
    with pytest.raises(Denied):
        Files(alias)


def test_root_permission_rejection(root):
    root.chmod(0o770)
    with pytest.raises(Denied):
        Files(root)


def test_lock_contention_bounded(root):
    with Files(root) as first, Files(root) as second, first.lock():
        with pytest.raises(BlockingIOError):
            Jobs(second, 'qa-security').begin(REQUEST, CANDIDATE)


def test_manifest_identity_tamper(root):
    with Files(root) as files:
        jobs = Jobs(files, 'qa-security')
        job = jobs.begin(REQUEST, CANDIDATE)
        path = root / (job.job_id + '.json')
        data = json.loads(path.read_bytes())
        data['identity']['head'] = 'f' * 40
        path.write_text(json.dumps(data))
        with pytest.raises(Denied):
            jobs.load(job.job_id)


def test_atomic_write_failure_keeps_original(root, monkeypatch):
    def fail_replace(*args, **kwargs):
        raise OSError('injected rename failure')
    with Files(root) as files:
        files.write('current-1.json', b'original')
        monkeypatch.setattr(os, 'replace', fail_replace)
        with pytest.raises(OSError):
            files.write('current-1.json', b'replacement')
        assert (root / 'current-1.json').read_bytes() == b'original'
        assert list(root.glob('.tmp-*')) == []


def test_final_mode_and_state_must_agree(root):
    with Files(root) as files:
        jobs = Jobs(files, 'qa-security')
        job = jobs.begin(REQUEST, CANDIDATE)
        (root / (job.job_id + '.json')).chmod(0o400)
        with pytest.raises(Denied):
            jobs.load(job.job_id)


def test_interrupted_pointer_update_recovers_safely(root, monkeypatch):
    with Files(root) as files:
        jobs = Jobs(files, 'qa-security')
        old = jobs.begin(REQUEST, CANDIDATE)
        jobs.start(old.job_id, CANDIDATE)
        fresh = Candidate(pr=1, head='c' * 40, base=BASE)
        request = Request(pr=1, head=fresh.head)
        original = files.write
        def fail_pointer(name, payload, *, final=False):
            if name == 'current-1.json':
                raise OSError('injected pointer failure')
            return original(name, payload, final=final)
        monkeypatch.setattr(files, 'write', fail_pointer)
        with pytest.raises(OSError):
            jobs.begin(request, fresh)
        assert jobs.load(old.job_id).state == 'stale'
        monkeypatch.setattr(files, 'write', original)
        recovered = jobs.begin(request, fresh)
        assert recovered.state == 'queued'
        assert jobs.current(1) == recovered.job_id
        assert not jobs.eligible(old.job_id, CANDIDATE)
