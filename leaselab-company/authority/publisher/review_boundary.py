"""Fixed canary for the managed Codex tool sandbox; no secret bytes are read."""
import errno
import json
import os
import socket
import sys
from pathlib import Path


def open_denied(path: Path) -> bool:
    try:
        fd = os.open(path, os.O_RDONLY)
    except PermissionError:
        return True
    else:
        os.close(fd)
        return False


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit(2)
    home = Path('/opt/executor-home').read_text().strip()
    checks = {
        'home_canary_denied': open_denied(Path(home) / 'review-boundary-canary'),
        'auth_open_denied': open_denied(Path(home) / '.codex/auth.json'),
        'broker_absent': not Path('/run/leaselab-github/broker.sock').exists(),
        'evidence_absent': not Path('/var/lib/leaselab-publisher/evidence').exists(),
        'nonroot': os.getuid() != 0,
        'secret_env_absent': not any(name in os.environ for name in ('GH_TOKEN', 'GITHUB_TOKEN', 'OPENAI_API_KEY', 'CODEX_API_KEY')),
        'source_config_absent': not Path('/workspace/.codex/config.toml').exists(),
        'source_skills_absent': not Path('/workspace/.agents/skills').exists(),
        'head_readable': Path('/workspace').is_dir(),
        'base_readable': Path('/base').is_dir(),
    }
    try:
        with socket.create_connection(('1.1.1.1', 443), timeout=1):
            checks['network_denied'] = False
    except OSError as error:
        checks['network_denied'] = error.errno in (errno.ENETUNREACH, errno.EPERM, errno.EACCES)
    try:
        _ = Path('/workspace/forbidden-write').write_text('synthetic')
        checks['source_write_denied'] = False
    except OSError as error:
        checks['source_write_denied'] = error.errno in (errno.EROFS, errno.EACCES)
    print(json.dumps(checks, sort_keys=True))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == '__main__':
    main()
