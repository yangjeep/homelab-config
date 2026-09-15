#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: fixed installed launcher invokes this inside its isolated namespace.
"""Synthetic boundary probes; never reads any credential contents."""
import json
import os
import socket
import sys
import time
from pathlib import Path


def readable(path: Path) -> bool:
    try:
        with path.open('rb') as stream:
            _ = stream.read(1)
        return True
    except OSError:
        return False


def writable(path: Path) -> bool:
    try:
        with path.open('wb') as stream:
            _ = stream.write(b'synthetic attempt')
        return True
    except OSError:
        return False


def main() -> int:
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in ('codex-canary', 'test-canary'):
        return 2
    lane = sys.argv[1]
    home = sys.argv[2] if len(sys.argv) == 3 else Path('/opt/executor-home').read_text().strip()
    checks = {
        'source_read': Path('/workspace/source.txt').read_text() == 'synthetic immutable source\n',
        'source_write_denied': not writable(Path('/workspace/source.txt')),
        'auth_read_denied': not readable(Path(home) / '.codex/auth.json'),
        'publisher_socket_absent': not Path('/run/leaselab-github/broker.sock').exists(),
        'merge_socket_absent': not Path('/run/leaselab-merge/merge.sock').exists(),
        'evidence_absent': not Path('/var/lib/leaselab-publisher/evidence').exists(),
        'secret_env_absent': not any(name in os.environ for name in (
            'GH_TOKEN', 'GITHUB_TOKEN', 'OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENROUTER_API_KEY')),
    }
    if lane == 'codex-canary':
        checks['proc_control_memory_denied'] = not readable(Path('/proc/1/mem'))
        checks['proc_namespace_bounded'] = len([p for p in Path('/proc').iterdir() if p.name.isdigit()]) < 8
        checks['proc_root_auth_denied'] = not readable(Path('/proc/1/root') / home.lstrip('/') / '.codex/auth.json')
        try:
            parent_sink = os.readlink('/proc/1/fd/1')
            own_sink = os.readlink('/proc/self/fd/1')
            same_tool_output = parent_sink == own_sink and parent_sink.startswith(('/dev/pts/', 'pipe:['))
        except OSError:
            same_tool_output = False
        checks['proc_stdout_safe'] = same_tool_output or not writable(Path('/proc/1/fd/1'))

    else:
        checks['scratch_write'] = writable(Path('/scratch/canary-output'))
        checks['auth_home_absent'] = not Path(home).exists()
        checks['pid_namespace'] = len([p for p in Path('/proc').iterdir() if p.name.isdigit()]) < 8
    try:
        with socket.create_connection(('192.0.2.1', 45679), timeout=1):
            checks['network_denied'] = False
    except OSError as error:
        checks['network_denied'] = error.errno in (1, 13, 101)
    print(json.dumps(checks, sort_keys=True), flush=True)
    # Keep a synthetic process alive briefly for the external role-UID probe.
    time.sleep(12)
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
