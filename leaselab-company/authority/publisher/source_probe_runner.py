#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic==2.12.5"]
# ///
# How to run: root invokes with the same fixed H/B JSON as source_supervisor.
"""Reuse executor UID/capture boundary for immutable review and auth-free test probes."""
import fcntl
import hashlib
import json
import os
import pwd
import secrets
import sys
from pathlib import Path

from executor_capture import capture
from executor_config import CODE, executor
from executor_launch import trusted
from publisher_models import Denied
from source_models import Pair


def main() -> None:
    if os.geteuid() != 0 or len(sys.argv) != 2 or len(sys.argv[1]) > 200:
        raise Denied
    pair = Pair.model_validate_json(sys.argv[1])
    source_id = hashlib.sha256(pair.model_dump_json().encode()).hexdigest()
    source = Path('/var/lib/leaselab-publisher/sources') / source_id
    trusted(source, directory=True)
    trusted(source / 'pair.json')
    if Pair.model_validate_json((source / 'pair.json').read_bytes()) != pair:
        raise Denied
    trusted(CODE / 'source_probe.py')
    for role, lane in (('reviewer', 'review'), ('qa-security', 'test')):
        selected = executor(role)
        with (selected.root / 'lock').open('r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            identity = pwd.getpwnam(selected.user)
            job_id = secrets.token_hex(32)
            evidence = Path('/var/lib/leaselab-publisher/evidence') / job_id
            evidence.mkdir(mode=0o700)
            args = ['/usr/bin/setpriv', '--no-new-privs', '/usr/sbin/runuser', '-u', selected.user,
                    '--', '/usr/bin/bwrap', '--unshare-all', '--die-with-parent', '--new-session',
                    '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
                    '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                    '--tmpfs', '/run', '--ro-bind', str(source / 'head'), '/workspace',
                    '--ro-bind', str(source / 'base'), '/base', '--ro-bind', str(CODE / 'source_probe.py'),
                    '/opt/source_probe.py', '--chdir', '/workspace']
            if lane == 'test':
                scratch = selected.root / 'work' / job_id
                scratch.mkdir(mode=0o700)
                os.chown(scratch, identity.pw_uid, identity.pw_gid)
                args += ['--bind', str(scratch), '/scratch']
            args += ['--', '/usr/bin/python3', '/opt/source_probe.py', lane]
            result = capture(args, evidence / 'output', timeout=30, maximum=16384)
            report = {'job': job_id, 'source_id': source_id, 'lane': lane, 'exit_code': result.exit_code,
                      'limited': result.limited, 'sha256': result.digest}
            with (evidence / 'source-result.json').open('x') as output:
                json.dump(report, output, sort_keys=True)
            (evidence / 'source-result.json').chmod(0o400)
            print(json.dumps(report))
            if result.exit_code != 0 or result.limited:
                raise Denied



if __name__ == '__main__':
    main()
