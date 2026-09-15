#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic==2.12.5"]
# ///
# How to run: root invokes this with one exact {head,base} JSON argument.
"""Root materialization command; never receives the fetch service's credential."""
import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path

from executor_capture import capture
from publisher_models import Denied, unique_keys
from source_models import Pair, Tree
from source_seal import metadata, seal


def main() -> None:
    if os.geteuid() != 0 or len(sys.argv) != 2 or len(sys.argv[1]) > 200:
        raise Denied
    pair = Pair.model_validate_json(sys.argv[1])
    json.loads(sys.argv[1], object_pairs_hook=unique_keys)
    root = Path('/var/lib/leaselab-publisher/sources')
    root.mkdir(mode=0o755, exist_ok=True)
    fd = os.open(root / 'lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        identity = hashlib.sha256(pair.model_dump_json().encode()).hexdigest()
        destination = root / identity
        destination.mkdir(mode=0o755)
        result = capture(['/usr/bin/setpriv', '--no-new-privs', '/usr/sbin/runuser', '-u',
                          'leaselab-source-fetch', '--', '/opt/leaselab-publisher-executor/venv/bin/python',
                          '/usr/local/libexec/leaselab-company/publisher/source_main.py', pair.model_dump_json()],
                         destination / 'fetch-output', timeout=180, maximum=65536)
        if result.exit_code != 0 or result.limited:
            raise Denied
        incoming = Path('/var/lib/leaselab-publisher/source-fetch') / identity
        fetched = Pair.model_validate_json(metadata(incoming / 'pair.json', 200))
        if fetched != pair:
            raise Denied
        for lane in ('head', 'base'):
            raw = metadata(incoming / (lane + '.tree.json'), 8388608)
            if len(raw) > 8388608:
                raise Denied
            tree = Tree.model_validate_json(raw)
            seal(incoming / lane, destination / lane, tree)
            with (destination / (lane + '.tree.json')).open('xb') as output:
                _ = output.write(raw)
            (destination / (lane + '.tree.json')).chmod(0o444)
        with (destination / 'pair.json').open('x') as output:
            _ = output.write(pair.model_dump_json())
            output.flush()
            os.fsync(output.fileno())
        (destination / 'pair.json').chmod(0o444)
        destination.chmod(0o555)
        print(json.dumps({'source_id': identity, 'head': pair.head, 'base': pair.base}))


if __name__ == '__main__':
    try:
        main()
    except (Denied, OSError, ValueError, KeyError):
        print('SOURCE_MATERIALIZATION_DENIED', file=sys.stderr)
        raise SystemExit(1) from None
