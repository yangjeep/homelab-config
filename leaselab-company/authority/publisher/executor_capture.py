"""Bound output and lifetime; only the root supervisor writes evidence."""
import hashlib
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Capture:
    exit_code: int
    digest: str
    size: int
    limited: bool


def capture(argv: list[str], target: Path, *, timeout: float = 180, maximum: int = 1048576) -> Capture:
    digest = hashlib.sha256()
    size = 0
    limited = False
    deadline = time.monotonic() + timeout
    with target.open('xb', buffering=0) as output:
        os.chmod(target, 0o600)
        with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, close_fds=True, start_new_session=True,
                              env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'}) as process:
            assert process.stdout is not None
            with selectors.DefaultSelector() as selector:
                _ = selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        limited = True
                        break
                    if not selector.select(min(remaining, 0.25)):
                        continue
                    chunk = os.read(process.stdout.fileno(), min(65536, maximum - size + 1))
                    if not chunk:
                        break
                    if size + len(chunk) > maximum:
                        limited = True
                        break
                    _ = output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            # Kill the complete invocation group even if the main process exited.
            # The outer bwrap --die-with-parent also tears down the PID namespace.
            try:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                _ = process.wait()
            code = process.wait()
        os.fsync(output.fileno())
    target.chmod(0o400)
    return Capture(code, digest.hexdigest(), size, limited)
