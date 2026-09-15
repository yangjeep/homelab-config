#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: git config credential.helper /usr/local/bin/leaselab-git-credential
"""Git credential protocol: exact HTTPS repository, no persistent token storage."""
import re
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from policy import Denied, SOCKET


def credential_request(raw: bytes) -> None:
    if len(raw) > 8192:
        raise Denied
    fields: dict[str, str] = {}
    for line in raw.decode('utf-8').splitlines():
        if not line:
            break
        key, separator, value = line.partition('=')
        if not separator or key in fields:
            raise Denied
        fields[key] = value
    if (fields.get('protocol') != 'https' or fields.get('host') != 'github.com'
            or fields.get('path') not in ('yangjeep/leaselab', 'yangjeep/leaselab.git')):
        raise Denied


def obtain() -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(25)
        connection.connect(SOCKET)
        connection.sendall(b'get\n')
        connection.shutdown(socket.SHUT_WR)
        response = bytearray()
        while len(response) <= 513:
            part = connection.recv(514 - len(response))
            if not part:
                break
            response.extend(part)
    token = bytes(response).decode('ascii')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{10,512}\n', token):
        raise Denied
    return token.rstrip('\n')


def main() -> int:
    if sys.argv[1:] in (['store'], ['erase']):
        return 0
    if sys.argv[1:] != ['get']:
        return 1
    try:
        credential_request(sys.stdin.buffer.read(8193))
        token = obtain()
    except (Denied, OSError, ValueError):
        return 1
    sys.stdout.write(f'username=x-access-token\npassword={token}\n\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
