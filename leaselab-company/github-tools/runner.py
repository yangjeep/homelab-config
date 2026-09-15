#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: root-owned SSH forced command invokes python3 -I runner.py.
"""Fixed SSH command dispatcher; only the CoS Unix UID can use its broker token."""
import importlib.util
import json
import os
from pathlib import Path
import pwd
import signal
import sys
from types import FrameType

# Resolve sibling package from the trusted root-owned install, ignoring PYTHONPATH.
PACKAGE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('company_github_runtime', PACKAGE / '__init__.py')
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
from company_github_runtime.operations import Denied, execute, parse_request
from company_github_runtime.transport import MARKER, TransportFailure


def deadline(_signal: int, _frame: FrameType | None) -> None:
    raise TimeoutError


def main() -> int:
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(45)
    try:
        if (os.getuid() == 0 or os.getuid() != pwd.getpwnam('leaselab-chief-of-staff').pw_uid
                or os.environ.get('SSH_ORIGINAL_COMMAND') != MARKER):
            raise Denied
        raw = sys.stdin.buffer.read(8193)
        if len(raw) > 8192:
            raise Denied
        request = parse_request(json.loads(raw))
        result = execute(request)
        json.loads(result)
        sys.stdout.write(result)
        return 0
    except (Denied, TransportFailure, OSError, ValueError, KeyError):
        # No untrusted request, gh stderr, bearer credential or API body in errors.
        return 1
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())
