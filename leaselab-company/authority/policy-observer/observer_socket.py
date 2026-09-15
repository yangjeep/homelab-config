"""Linux authenticated request framing; no identity or path claims in request body."""
import socket
import struct
import sys
from collections.abc import Callable

from observer_models import Denied, Request
from observer_policy import Reader, observe
from pydantic import ValidationError


def authorize(connection: socket.socket, merge_uid: int) -> Request:
    if not sys.platform.startswith('linux'):
        raise Denied('Linux peer credentials required')
    uid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
    if uid != merge_uid:
        raise Denied('peer denied')
    connection.settimeout(2)
    raw = bytearray()
    while len(raw) <= 256:
        part = connection.recv(257 - len(raw))
        if not part:
            break
        raw.extend(part)
    if len(raw) > 256:
        raise Denied('request too large')
    return Request.model_validate_json(raw)


def serve(connection: socket.socket, merge_uid: int, factory: Callable[[], Reader]) -> None:
    try:
        request = authorize(connection, merge_uid)
        result = observe(factory(), request)
        raw = result.model_dump_json().encode() + b'\n'
        if len(raw) > 2000000:
            raise Denied('response too large')
    except (Denied, ValidationError, OSError):
        raw = b'{"error":"policy_unavailable"}\n'
    connection.sendall(raw)
