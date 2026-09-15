"""Fixed CoS SSH transport with bounded output and no diagnostic disclosure."""
import os
import selectors
import subprocess
import time
from typing import Final

MARKER: Final = 'leaselab-company-github-v1'
SSH: Final = (
    '/usr/bin/ssh', '-F', '/dev/null', '-T', '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
    '-o', 'IdentityAgent=none', '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
    '-o', 'ConnectTimeout=5', '-o', 'UserKnownHostsFile=/home/hermes/.ssh/known_hosts',
    '-i', '/etc/leaselab-company/ssh/chief-of-staff', '-p', '22',
    'leaselab-chief-of-staff@127.0.0.1', MARKER,
)


class TransportFailure(Exception):
    """Operation failed or mutation outcome could not be determined."""


def capture(arguments: list[str], payload: bytes) -> str:
    """Bound execution and output; discard stderr, never return raw exceptions."""
    if len(payload) > 8192:
        raise TransportFailure
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'}
    with subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=environment) as process:
        assert process.stdin is not None and process.stdout is not None
        end = time.monotonic() + 40
        output = bytearray()
        try:
            # Tool input is <=8192 bytes; all writes remain data, never shell source.
            process.stdin.write(payload)
            process.stdin.close()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = end - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise TransportFailure
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > 32768:
                        raise TransportFailure
            if process.wait(timeout=max(0.01, end - time.monotonic())) != 0:
                raise TransportFailure
        except (TransportFailure, OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()
            raise TransportFailure from None
    return bytes(output).decode('utf-8')
