"""Linux distinct-UID fake observer; no production socket, key or service."""
import json
import os
import select
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'authority/merge'))
sys.path.insert(0, str(ROOT / 'authority/policy-observer'))
from merge_observer import exchange
from merge_policy import Denied
from test_merge_observer import packet


@pytest.mark.skipif(not sys.platform.startswith('linux') or os.geteuid() != 0,
                    reason='Linux root runner required for distinct server UID')
@pytest.mark.parametrize('mutation', ['valid', 'wrong_uid', 'nonce', 'oversize', 'stale'])
def test_socket_verifies_server_and_fresh_response(mutation):
    # Given: a temporary observer server running as UID65534, with synthetic policy.
    data, _ = packet.__wrapped__()
    ready_read, ready_write = os.pipe()
    with tempfile.TemporaryDirectory(prefix='leaselab-merge-observer-peer-') as directory:
        os.chown(directory, 65534, 65534)
        path = str(Path(directory) / 'observer.sock')
        pid = os.fork()
        if pid == 0:
            os.close(ready_read)
            os.setgroups([])
            os.setgid(65534)
            os.setuid(65534)
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                    listener.bind(path)
                    listener.listen(1)
                    listener.settimeout(5)
                    os.write(ready_write, b'ready')
                    os.close(ready_write)
                    with listener.accept()[0] as connection:
                        connection.settimeout(5)
                        request = bytearray()
                        while chunk := connection.recv(256):
                            request.extend(chunk)
                        data['nonce'] = json.loads(request)['nonce']
                        data['observed_at'] = datetime.now(timezone.utc).isoformat()
                        if mutation == 'nonce':
                            data['nonce'] = 'b' * 64
                        if mutation == 'stale':
                            data['observed_at'] = '2020-01-01T00:00:00+00:00'
                        raw = json.dumps(data).encode() + b'\n'
                        if mutation == 'oversize':
                            raw = b'x' * 2000001
                        connection.sendall(raw)
            except (OSError, json.JSONDecodeError):
                os._exit(0 if mutation in ('wrong_uid', 'oversize') else 1)
            os._exit(0)
        os.close(ready_write)
        try:
            assert select.select([ready_read], [], [], 5)[0]
            assert os.read(ready_read, 5) == b'ready'
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(5)
                connection.connect(path)
                # When / Then: kernel identity, nonce, byte limit and freshness are enforced.
                if mutation == 'valid':
                    assert exchange(connection, 65534)[0].id == 1
                else:
                    with pytest.raises((Denied, ValidationError)):
                        exchange(connection, 65533 if mutation == 'wrong_uid' else 65534)
        finally:
            os.close(ready_read)
            _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
