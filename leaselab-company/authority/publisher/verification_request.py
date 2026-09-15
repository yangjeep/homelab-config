"""Systemd entry: only a root-owned bounded request file may select PR/head."""
import os
import re
import sys
from pathlib import Path

from executor_launch import trusted
from publisher_models import Denied, parse_request
from verification_run import run


def main() -> None:
    if os.geteuid() != 0 or len(sys.argv) != 2 or not re.fullmatch('[0-9a-f]{64}', sys.argv[1]):
        raise Denied
    root = Path('/var/lib/leaselab-publisher/verification-requests')
    trusted(root, directory=True)
    path = root / sys.argv[1]
    trusted(path)
    with path.open('rb') as stream:
        raw = stream.read(257)
    _ = parse_request(raw)
    run(raw.decode())


if __name__ == '__main__':
    try:
        main()
    except (Denied, OSError, ValueError):
        print('VERIFICATION_DENIED', file=sys.stderr)
        raise SystemExit(1) from None
