"""Auth-free stdlib-only runner. No repository code, hooks or dependencies execute."""
import errno
import os
import socket
from pathlib import Path


def main() -> None:
    if os.getuid() == 0 or any(Path(path).exists() for path in (
            '/run/leaselab-github/broker.sock', '/etc/leaselab-company',
            '/srv/leaselab', '/var/lib/leaselab-publisher', '/root/.codex')):
        raise SystemExit(3)
    try:
        with socket.create_connection(('1.1.1.1', 443), timeout=1):
            raise SystemExit(3)
    except OSError as error:
        if error.errno not in (errno.ENETUNREACH, errno.EPERM, errno.EACCES):
            raise SystemExit(3)
    try:
        _ = Path('/workspace/unauthorized-write').write_bytes(b'no')
        raise SystemExit(3)
    except OSError as error:
        if error.errno not in (errno.EROFS, errno.EACCES):
            raise SystemExit(3)
    paths = Path('/recipe.txt').read_text().splitlines()
    for relative in paths:
        raw = (Path('/workspace') / relative).read_bytes()
        if not raw or len(raw) > 1048576 or b'\0' in raw:
            raise SystemExit(2)
        text = raw.decode('utf-8')
        if not text.endswith('\n') or any(line.startswith(('<<<<<<< ', '=======', '>>>>>>> ')) for line in text.splitlines()):
            raise SystemExit(2)
    _ = Path('/scratch/completed').write_text('docs-text-v1\n')
    print('DOCUMENT_SYNTAX_CHECK_COMPLETED')


if __name__ == '__main__':
    main()
