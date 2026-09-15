"""Construct a fixed, credential-separated bubblewrap execution boundary."""
import hashlib
import os
import pwd
import stat
from pathlib import Path

from executor_config import CODE, CODEX, Executor, Lane
from publisher_models import Denied


def trusted(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    correct_kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not correct_kind or info.st_uid != 0 or info.st_mode & 0o022 or info.st_nlink != 1 and not directory:
        raise Denied


def command(executor: Executor, job: Path, lane: Lane) -> list[str]:
    trusted(CODE, directory=True)
    trusted(CODE / 'executor_canary.py')
    trusted(CODEX)
    trusted(CODE / 'codex.sha256')
    expected = (CODE / 'codex.sha256').read_text().strip()
    with CODEX.open('rb') as binary:
        actual = hashlib.file_digest(binary, 'sha256').hexdigest()
    if expected != actual:
        raise Denied
    trusted(job, directory=True)
    trusted(job / 'source', directory=True)
    trusted(job / 'source/source.txt')
    if sorted(p.name for p in (job / 'source').iterdir()) != ['source.txt']:
        raise Denied
    config = CODE / 'executor-config' / (executor.role + '.toml')
    trusted(config)
    args = ['/usr/bin/setpriv', '--no-new-privs', '/usr/sbin/runuser', '-u', executor.user, '--', '/usr/bin/bwrap',
            '--unshare-all', '--die-with-parent', '--new-session',
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
            '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/run',
            '--tmpfs', '/etc', '--ro-bind', '/etc/passwd', '/etc/passwd',
            '--ro-bind', '/etc/group', '/etc/group',
            '--ro-bind', str(job / 'source'), '/workspace',
            '--ro-bind', str(CODE / 'executor_canary.py'), '/opt/executor_canary.py',
            '--ro-bind', str(CODE / 'executor-config' / (executor.role + '.home')), '/opt/executor-home',
            '--chdir', '/workspace']
    if lane == 'test-canary':
        return args + ['--bind', str(job / 'scratch'), '/scratch', '--',
                       '/usr/bin/python3', '/opt/executor_canary.py', lane, str(executor.home)]
    args += ['--share-net', '--bind', str(executor.home), str(executor.home),
             '--ro-bind', str(job / 'source'), str(executor.home / '.codex/tmp'),
             '--dir', '/etc/codex', '--ro-bind', str(config), '/etc/codex/requirements.toml',
             '--ro-bind', '/etc/ssl', '/etc/ssl', '--ro-bind', '/etc/resolv.conf', '/etc/resolv.conf',
             '--ro-bind', '/etc/hosts', '/etc/hosts', '--', str(CODEX)]
    if lane == 'codex-canary':
        return args + ['sandbox', '--include-managed-config', '-P', 'verifier', '-C', '/workspace',
                       '/usr/bin/python3', '/opt/executor_canary.py', lane, str(executor.home)]
    return args + ['exec', '--sandbox', 'read-only', '--ignore-user-config', '--ignore-rules',
                   '--ephemeral', '--json', '--skip-git-repo-check', '-C', '/workspace',
                   '-c', 'approval_policy="never"', '-c', 'web_search="disabled"',
                   '-c', 'features.plugins=false', '-c', 'features.apps=false',
                   'Run the root-managed synthetic boundary canary: python3 /opt/executor_canary.py codex-canary. ' +
                   'It verifies expected permission denials without reading credential contents. Do not change permissions. ' +
                   'If the command exits zero and all checks are true, reply exactly EXECUTOR_AUTH_AND_BOUNDARY_OK.']


def prepare(executor: Executor, job_id: str) -> Path:
    identity = pwd.getpwnam(executor.user)
    if identity.pw_uid == 0 or identity.pw_gid == 0:
        raise Denied
    job = executor.root / 'work' / job_id
    job.mkdir(mode=0o750)
    os.chown(job, 0, identity.pw_gid)
    job.chmod(0o750)
    source = job / 'source'
    source.mkdir(mode=0o750)
    os.chown(source, 0, identity.pw_gid)
    _ = (source / 'source.txt').write_text('synthetic immutable source\n')
    os.chown(source / 'source.txt', 0, identity.pw_gid)
    (source / 'source.txt').chmod(0o440)
    source.chmod(0o550)
    scratch = job / 'scratch'
    scratch.mkdir(mode=0o700)
    os.chown(scratch, identity.pw_uid, identity.pw_gid)
    return job
