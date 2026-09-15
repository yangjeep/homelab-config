"""Root-only integrated observation, source, manifest and isolated verification."""
import fcntl
import hashlib
import json
import os
import pwd
import secrets
import sys
from pathlib import Path

from executor_capture import Capture, capture
from executor_config import CODE, executor
from executor_launch import trusted
from publisher_files import Files
from publisher_jobs import TERMINAL, Jobs
from publisher_models import Candidate, Completion, Denied, parse_request
from review_models import ReviewIdentity
from review_run import review
from source_models import Pair, Tree
from verification_recipe import RECIPE, changes

ROOT = Path('/var/lib/leaselab-publisher')
PYTHON = '/opt/leaselab-publisher-executor/venv/bin/python'


def policy_digest() -> str:
    digest = hashlib.sha256()
    for name in ('verification_run.py', 'verification_recipe.py', 'verification_test.py', 'verification_observe.py',
                 'review_models.py', 'review_events.py', 'review_launch.py', 'review_run.py',
                 'review_boundary.py', 'review-schema.json', 'executor-config/reviewer.toml', 'codex.sha256'):
        trusted(CODE / name)
        digest.update(name.encode())
        digest.update((CODE / name).read_bytes())
    return digest.hexdigest()


def policy_file(paths: tuple[str, ...], job_id: str) -> Path:
    selected = executor('qa-security')
    account = pwd.getpwnam(selected.user)
    directory = selected.root / 'work' / (job_id + '-policy')
    directory.mkdir(mode=0o750)
    os.chown(directory, 0, account.pw_gid)
    directory.chmod(0o750)
    path = directory / 'recipe.txt'
    _ = path.write_text('\n'.join(paths) + '\n')
    os.chown(path, 0, account.pw_gid)
    path.chmod(0o440)
    return path


def observe(raw: str, output: Path) -> Candidate:
    result = capture(['/usr/bin/setpriv', '--no-new-privs', '/usr/sbin/runuser', '-u',
                      'leaselab-source-fetch', '--', PYTHON, str(CODE / 'verification_observe.py'), raw],
                     output, timeout=45, maximum=1024)
    if result.exit_code != 0 or result.limited:
        raise Denied
    return Candidate.model_validate_json(output.read_bytes())


def materialize(value: Candidate, output: Path) -> Path:
    pair = Pair(head=value.head, base=value.base)
    source = ROOT / 'sources' / hashlib.sha256(pair.model_dump_json().encode()).hexdigest()
    if not source.exists():
        result = capture([PYTHON, str(CODE / 'source_supervisor.py'), pair.model_dump_json()],
                         output, timeout=200, maximum=4096)
        if result.exit_code != 0 or result.limited:
            raise Denied
    trusted(source, directory=True)
    trusted(source / 'pair.json')
    if Pair.model_validate_json((source / 'pair.json').read_bytes()) != pair:
        raise Denied
    return source


def test_command(source: Path, recipe: Path, scratch: Path) -> list[str]:
    selected = executor('qa-security')
    for path in (CODE / 'verification_test.py', recipe):
        trusted(path)
    return ['/usr/bin/setpriv', '--no-new-privs', '/usr/sbin/runuser', '-u', selected.user,
            '--', '/usr/bin/bwrap', '--unshare-all', '--die-with-parent', '--new-session',
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
            '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
            '--tmpfs', '/run', '--ro-bind', str(source / 'head'), '/workspace',
            '--ro-bind', str(source / 'base'), '/base', '--bind', str(scratch), '/scratch',
            '--ro-bind', str(recipe), '/recipe.txt', '--ro-bind', str(CODE / 'verification_test.py'),
            '/opt/test.py', '--chdir', '/workspace', '--', '/usr/bin/python3', '-I', '/opt/test.py']


def finish(jobs: Jobs, job_id: str, current: Candidate, evidence: Path, result: Capture | None, *, error: bool = False, semantic: str | None = None) -> None:
    report = {'recipe': RECIPE, 'policy_sha256': policy_digest(),
              'runner_sha256': hashlib.sha256((CODE / 'verification_test.py').read_bytes()).hexdigest(),
              'candidate': jobs.load(job_id).identity.model_dump(), 'final_observation': current.model_dump(), 'job': job_id,
              'test_exit': result.exit_code if result else None,
              'limited': result.limited if result else False,
              'output_sha256': result.digest if result else None,
              'semantic_digest': semantic, 'authorization': 'blocked', 'reason': 'supervisor-error-or-interrupted' if error else ('trusted-check-publication-not-implemented' if semantic else ('independent-disposition-not-implemented' if result else 'unsupported-recipe'))}
    payload = json.dumps(report, sort_keys=True).encode()
    with (evidence / 'verification.json').open('xb') as output:
        _ = output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    (evidence / 'verification.json').chmod(0o400)
    state = 'failed' if error or (result and (result.exit_code != 0 or result.limited)) else 'blocked'
    manifest = jobs.complete(job_id, current, Completion(state=state, evidence_digest=hashlib.sha256(payload).hexdigest()))
    print(json.dumps({'job': job_id, 'evidence': evidence.name, 'state': manifest.state, 'test_exit': report['test_exit']}))
    raise SystemExit(2 if manifest.state == 'failed' else 3)


def run(raw: str) -> None:
    request = parse_request(raw.encode())
    selected = executor('qa-security')
    with (selected.root / 'lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        staging = ROOT / 'verification-observations'
        staging.mkdir(mode=0o700, exist_ok=True)
        initial = observe(raw, staging / secrets.token_hex(32))
        stores = ROOT / 'verification-stores'
        stores.mkdir(mode=0o700, exist_ok=True)
        store = stores / policy_digest()
        store.mkdir(mode=0o700, exist_ok=True)
        with Files(store) as files:
            jobs = Jobs(files, 'qa-security')
            manifest = jobs.begin(request, initial)
            if manifest.state in TERMINAL:
                print(json.dumps({'job': manifest.job_id, 'state': manifest.state, 'deduplicated': True}))
                raise SystemExit(2 if manifest.state == 'failed' else 3)
            evidence_id = hashlib.sha256((manifest.job_id + policy_digest()).encode()).hexdigest()
            evidence = ROOT / 'evidence' / evidence_id
            if manifest.state == 'running':
                recovery = ROOT / 'evidence' / secrets.token_hex(32)
                recovery.mkdir(mode=0o700)
                finish(jobs, manifest.job_id, initial, recovery, None, error=True)
            evidence.mkdir(mode=0o700)
            _ = jobs.start(manifest.job_id, initial)
            result: Capture | None = None
            try:
                source = materialize(initial, evidence / 'materialize-output')
                for lane in ('head', 'base'):
                    trusted(source / (lane + '.tree.json'))
                try:
                    paths = changes(Tree.model_validate_json((source / 'head.tree.json').read_bytes()),
                                    Tree.model_validate_json((source / 'base.tree.json').read_bytes()))
                except Denied:
                    finish(jobs, manifest.job_id, observe(raw, evidence / 'final-observation'), evidence, None)
                    return
                recipe = policy_file(paths, evidence_id)
                scratch = selected.root / 'work' / evidence_id
                scratch.mkdir(mode=0o700)
                account = pwd.getpwnam(selected.user)
                os.chown(scratch, account.pw_uid, account.pw_gid)
                result = capture(test_command(source, recipe, scratch), evidence / 'test-output', timeout=30, maximum=65536)
                semantic = None
                if result.exit_code == 0 and not result.limited:
                    identity = ReviewIdentity(provenance='github', pr=initial.pr, head=initial.head, base=initial.base,
                                              policy=policy_digest(), source=source.name, job=evidence_id)
                    semantic = review(source, identity, paths, evidence)
                finish(jobs, manifest.job_id, observe(raw, evidence / 'final-observation'), evidence, result, semantic=semantic)
            except (Denied, OSError, ValueError):
                finish(jobs, manifest.job_id, initial, evidence, result, error=True)



def main() -> None:
    if os.geteuid() != 0 or len(sys.argv) != 2:
        raise Denied
    for name in ('verification_recipe.py', 'verification_observe.py', 'verification_run.py'):
        trusted(CODE / name)
    run(sys.argv[1])


if __name__ == '__main__':
    try:
        main()
    except (Denied, OSError, ValueError):
        print('VERIFICATION_DENIED', file=sys.stderr)
        raise SystemExit(1) from None
