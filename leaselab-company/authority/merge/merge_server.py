#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic>=2.10,<3"]
# ///
# How to run: service venv python -I /usr/local/lib/leaselab-merge/merge_server.py
"""Serial Linux peer-authenticated Reviewer merge service."""
import fcntl
import http.client
import os
import pwd
import signal
import socket
import stat
import struct
import subprocess
import sys
from pathlib import Path
from types import FrameType
from typing import Final

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_models import Policy, Request
from merge_policy import Denied, execute
from merge_transport import Client
from policy import Denied as CredentialDenied

SOCKET: Final = '/run/leaselab-merge/merge.sock'
POLICY: Final = Path('/etc/leaselab-company/merge/policy.json')


def load_policy() -> Policy:
    with os.fdopen(os.open(POLICY, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o640):
            raise Denied
        return Policy.model_validate_json(stream.read(8193))


def authorize(connection: socket.socket, reviewer_uid: int) -> Request:
    if not sys.platform.startswith('linux') or reviewer_uid in (0, os.geteuid()):
        raise Denied
    uid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
    if uid != reviewer_uid:
        raise Denied
    connection.settimeout(2)
    raw = bytearray()
    while len(raw) <= 256:
        part = connection.recv(257 - len(raw))
        if not part:
            break
        raw.extend(part)
    if len(raw) > 256:
        raise Denied
    return Request.model_validate_json(raw)


def deadline(_number: int, _frame: FrameType | None) -> None:
    raise TimeoutError


def main() -> int:
    if os.geteuid() != pwd.getpwnam('leaselab-merge').pw_uid or os.geteuid() == 0:
        raise Denied
    reviewer_uid = pwd.getpwnam('leaselab-reviewer').pw_uid
    _ = signal.signal(signal.SIGALRM, deadline)
    # RuntimeDirectory is writable only by service UID; no role can replace socket.
    with open('/run/leaselab-merge/instance.lock', 'a') as lock, socket.socket(
            socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        Path(SOCKET).unlink(missing_ok=True)
        listener.bind(SOCKET)
        os.chmod(SOCKET, 0o660)
        listener.listen(4)
        while True:
            connection = listener.accept()[0]
            with connection:
                _ = signal.alarm(120)
                try:
                    request = authorize(connection, reviewer_uid)
                    policy = load_policy()
                    if not policy.enabled:
                        raise Denied
                    result = execute(Client(), request, policy)
                    response = result.model_dump_json().encode() + b'\n'
                    print('merge.completed', request.pr, request.head, result.sha, flush=True)
                except (Denied, CredentialDenied, ValidationError, ValueError, OSError,
                        subprocess.SubprocessError, http.client.HTTPException):
                    # A response may be lost after GitHub accepts: never auto-retry writes.
                    response = b'{"error":"denied_or_indeterminate; inspect PR before retry"}\n'
                    print('merge.denied_or_indeterminate', flush=True)
                finally:
                    _ = signal.alarm(0)
                try:
                    connection.sendall(response)
                except OSError:
                    print('merge.response_disconnected', flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
