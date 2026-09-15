"""Real Linux distinct-UID Unix socket probe; synthetic policy, no service install."""
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authority/policy-observer'))
from observer_socket import serve
from test_policy_observer import NONCE, REQUEST, Fake


@pytest.mark.skipif(not sys.platform.startswith('linux') or os.geteuid() != 0,
                    reason='Linux root test runner needed to drop a child to nobody')
@pytest.mark.parametrize('trusted', [True, False])
def test_distinct_uid_when_kernel_authenticates_peer(trusted):
    # Given: root-owned temporary listener and an unprivileged test client.
    with tempfile.TemporaryDirectory(prefix='leaselab-observer-peer-') as directory:
        os.chmod(directory, 0o755)
        path = str(Path(directory) / 'probe.sock')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(path)
            os.chmod(path, 0o666)
            listener.listen(1)
            listener.settimeout(5)
            pid = os.fork()
            if pid == 0:
                listener.close()
                os.setgroups([])
                os.setgid(65534)
                os.setuid(65534)
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.settimeout(5)
                        client.connect(path)
                        client.sendall(REQUEST.model_dump_json().encode())
                        client.shutdown(socket.SHUT_WR)
                        payload = json.loads(client.recv(2000000))
                    valid = payload.get('nonce') == NONCE if trusted else payload == {'error': 'policy_unavailable'}
                except (OSError, json.JSONDecodeError):
                    # Denial before reading may reset the connection with unread data.
                    valid = not trusted
                os._exit(0 if valid else 1)
            reader = Fake()
            # When: the production handler receives SO_PEERCRED from a different UID.
            with listener.accept()[0] as connection:
                serve(connection, 65534 if trusted else 65533, lambda: reader)
            _, status = os.waitpid(pid, 0)
            # Then: only the configured UID reached the synthetic policy reader.
            assert os.waitstatus_to_exitcode(status) == 0
            assert bool(reader.calls) is trusted
