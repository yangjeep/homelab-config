"""Authenticated fresh policy reads; never imports observer credentials or transport."""
import os
import pwd
import secrets
import socket
import struct
import sys
import time
from datetime import datetime

sys.path.insert(0, '/usr/local/lib/leaselab-policy-observer')
from merge_models import Ruleset
from merge_policy import Denied
from observer_models import Observation, Request

SOCKET = '/run/leaselab-policy-observer/observer.sock'
MAX_BYTES = 2000000
MAX_SECONDS = 30


def decode(raw: bytes, binding: tuple[str, float]) -> tuple[Ruleset, ...]:
    nonce, started = binding
    if len(raw) > MAX_BYTES or not raw.endswith(b'\n') or raw.count(b'\n') != 1:
        raise Denied
    observation = Observation.model_validate_json(raw)
    if observation.nonce != nonce or 'repository' not in observation.model_fields_set:
        raise Denied
    observed = datetime.fromisoformat(observation.observed_at)
    if observed.tzinfo is None or not started - 0.001 <= observed.timestamp() <= time.time() + 1:
        raise Denied
    entries = observation.rulesets
    if not 0 < len(entries) <= 200 or len({entry.id for entry in entries}) != len(entries):
        raise Denied
    for entry in entries:
        if entry.source_type == 'Repository' and entry.source != 'yangjeep/leaselab':
            raise Denied
    return tuple(Ruleset.model_validate_json(entry.model_dump_json()) for entry in entries)


def exchange(connection: socket.socket, observer_uid: int) -> tuple[Ruleset, ...]:
    if not sys.platform.startswith('linux'):
        raise Denied
    uid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
    if uid != observer_uid:
        raise Denied
    nonce = secrets.token_hex(32)
    started = time.time()
    deadline = time.monotonic() + MAX_SECONDS
    connection.settimeout(MAX_SECONDS)
    connection.sendall(Request(nonce=nonce).model_dump_json().encode())
    connection.shutdown(socket.SHUT_WR)
    raw = bytearray()
    while len(raw) <= MAX_BYTES:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Denied
        connection.settimeout(remaining)
        part = connection.recv(min(65536, MAX_BYTES + 1 - len(raw)))
        if not part:
            break
        raw.extend(part)
    return decode(bytes(raw), (nonce, started))


def snapshot() -> tuple[Ruleset, ...]:
    uid = pwd.getpwnam('leaselab-policy-observer').pw_uid
    if uid in (0, os.geteuid()):
        raise Denied
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(SOCKET)
        return exchange(connection, uid)
