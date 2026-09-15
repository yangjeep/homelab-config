#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: installed service invokes /usr/bin/python3 -I broker.py.
"""Linux UID-authenticated, bounded, serial GitHub shell credential broker."""
import os
from pathlib import Path
import pwd
import socket
import signal
import struct
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from types import FrameType
import http.client

# -I excludes script directory; add only the root-owned installation directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from policy import Denied, ROLES, SOCKET, Role
from upstream import Token, mint


def parse_request(raw: bytes) -> None:
    if raw != b'get\n':
        raise Denied


def peer_uid(connection: socket.socket) -> int:
    if not sys.platform.startswith('linux'):
        raise Denied
    return struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]


def role_uids() -> Mapping[int, Role]:
    """Resolve fixed account names once; duplicate/root/service UIDs fail closed."""
    result: dict[int, Role] = {}
    for role in ROLES:
        uid = pwd.getpwnam('leaselab-' + role.name).pw_uid
        if uid in result or uid in (0, os.geteuid()):
            raise Denied
        result[uid] = role
    return result


class Broker:
    """Mutable token cache owned exclusively by the single serving loop."""
    def __init__(self, identities: Mapping[int, Role], issuer: Callable[[Role], Token] = mint) -> None:
        self.identities = identities
        self.issuer = issuer
        self.cache: dict[int, Token] = {}

    def token(self, uid: int) -> str:
        role = self.identities.get(uid)
        if uid == 0 or role is None or role.installation_id is None:
            raise Denied
        cached = self.cache.get(uid)
        if cached is None or cached.expires - time.time() <= 60:
            cached = self.issuer(role)
            self.cache[uid] = cached
        return cached.value

    def handle(self, connection: socket.socket) -> None:
        connection.settimeout(2)
        try:
            uid = peer_uid(connection)
            # EOF required: reject trailing requests/fields; 5 bytes bounds parsing.
            request = bytearray()
            while len(request) <= 4:
                part = connection.recv(5 - len(request))
                if not part:
                    break
                request.extend(part)
            parse_request(bytes(request))
            response = self.token(uid).encode('ascii') + b'\n'
        except (Denied, OSError, ValueError, subprocess.SubprocessError, http.client.HTTPException):
            response = b'error\n'
        try:
            connection.sendall(response)
        except OSError:
            return


def deadline(_signal: int, _frame: FrameType | None) -> None:
    raise TimeoutError


def main() -> int:
    try:
        service = Broker(role_uids())
        signal.signal(signal.SIGALRM, deadline)
        # RuntimeDirectory is private-writable by the service, never role users.
        Path(SOCKET).unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(SOCKET)
            os.chmod(SOCKET, 0o660)
            listener.listen(16)
            while True:
                connection, _ = listener.accept()
                with connection:
                    signal.alarm(20)
                    try:
                        service.handle(connection)
                    finally:
                        signal.alarm(0)
    except (Denied, KeyError, OSError):
        print('GitHub broker startup failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
