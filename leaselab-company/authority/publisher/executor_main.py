#!/usr/bin/python3
"""Root-only synthetic executor entry point. No caller verdict or arbitrary command."""
import fcntl
import json
import os
import secrets
import sys
from pathlib import Path

from executor_capture import capture
from executor_config import Lane, executor
from executor_launch import command, prepare, trusted
from publisher_models import Denied


def main() -> int:
    if os.geteuid() != 0 or len(sys.argv) != 3:
        raise Denied
    selected = executor(sys.argv[1])
    lane: Lane
    if sys.argv[2] == 'codex-canary':
        lane = 'codex-canary'
    elif sys.argv[2] == 'test-canary':
        lane = 'test-canary'
    elif sys.argv[2] == 'auth-smoke':
        lane = 'auth-smoke'
    else:
        raise Denied
    trusted(selected.root, directory=True)
    lock_path = selected.root / 'lock'
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        trusted(lock_path)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        job_id = secrets.token_hex(32)
        job = prepare(selected, job_id)
        evidence = Path('/var/lib/leaselab-publisher/evidence')
        trusted(evidence, directory=True)
        result_dir = evidence / job_id
        result_dir.mkdir(mode=0o700)
        result = capture(command(selected, job, lane), result_dir / 'output', timeout=180)
        manifest = result_dir / 'result.json'
        with manifest.open('x') as stream:
            json.dump({'role': selected.role, 'lane': lane, 'job': job_id,
                       'exit_code': result.exit_code, 'sha256': result.digest,
                       'size': result.size, 'limited': result.limited}, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        manifest.chmod(0o400)
        print(json.dumps({'job': job_id, 'exit_code': result.exit_code, 'limited': result.limited}))
        return 0 if result.exit_code == 0 and not result.limited else 1


if __name__ == '__main__':
    raise SystemExit(main())
