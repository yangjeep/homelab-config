"""Serial, disabled-by-default observer daemon; install only after explicit grant."""
import fcntl
import http.client
import os
import pwd
import signal
import socket
import stat
import subprocess
import sys
from pathlib import Path
from types import FrameType

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observer_models import Config, Denied
from observer_socket import serve
from observer_transport import Client
from policy import Denied as CredentialDenied

CONFIG = Path('/etc/leaselab-company/policy-observer/config.json')
SOCKET = '/run/leaselab-policy-observer/observer.sock'


def load_config() -> Config:
    with os.fdopen(os.open(CONFIG, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o640):
            raise Denied('untrusted configuration')
        raw = stream.read(8193)
        if len(raw) > 8192:
            raise Denied('oversized configuration')
        return Config.model_validate_json(raw)


def client() -> Client:
    try:
        return Client(load_config())
    except (CredentialDenied, ValueError, subprocess.SubprocessError, http.client.HTTPException) as error:
        raise Denied('credential unavailable') from error


def deadline(_number: int, _frame: FrameType | None) -> None:
    raise TimeoutError


def main() -> int:
    observer = pwd.getpwnam('leaselab-policy-observer').pw_uid
    merge_uid = pwd.getpwnam('leaselab-merge').pw_uid
    if os.geteuid() != observer or observer == 0 or merge_uid in (0, observer):
        raise Denied('service identity invalid')
    if not load_config().enabled:
        raise Denied('observer disabled')
    _ = signal.signal(signal.SIGALRM, deadline)
    with open('/run/leaselab-policy-observer/instance.lock', 'a') as lock, socket.socket(
            socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        Path(SOCKET).unlink(missing_ok=True)
        listener.bind(SOCKET)
        os.chmod(SOCKET, 0o660)
        listener.listen(4)
        while True:
            with listener.accept()[0] as connection:
                _ = signal.alarm(120)
                try:
                    serve(connection, merge_uid, client)
                except (OSError, http.client.HTTPException):
                    print('policy-observer.request_failed', flush=True)
                finally:
                    _ = signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())
