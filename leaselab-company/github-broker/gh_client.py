#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: leaselab-gh issue list --repo yangjeep/leaselab
"""Run the system GitHub CLI with only the caller's fixed installation token."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credential_helper import obtain
from policy import Denied


def main() -> int:
    try:
        token = obtain()
    except (Denied, OSError, ValueError):
        return 1
    environment = dict(os.environ)
    for key in ('GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN', 'GH_DEBUG'):
        environment.pop(key, None)
    environment.update(GH_TOKEN=token, GH_HOST='github.com', GH_PROMPT_DISABLED='1')
    os.execve('/usr/bin/gh', ['/usr/bin/gh', *sys.argv[1:]], environment)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
