#!/usr/bin/python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# How to run: root-owned source_probe_runner launches this in its auth-free namespace.
"""Exercise real exported repository bytes without executing repository code."""
import json
import os
import socket
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ('review', 'test'):
        return 2
    package = Path('/workspace/apps/leaselab-site/package.json')
    checks = {'real_leaselab_site_source': b'"name"' in package.read_bytes(),
              'base_source_present': Path('/base/apps/leaselab-site/package.json').is_file(),
              'no_git_metadata': not Path('/workspace/.git').exists(),
              'auth_not_mounted': not Path('/var/lib/leaselab-publisher/executor').exists(),
              'broker_not_mounted': not Path('/run/leaselab-github').exists(),
              'non_root': os.getuid() != 0}
    try:
        with package.open('ab') as output:
            _ = output.write(b'bad')
        checks['immutable_source'] = False
    except OSError:
        checks['immutable_source'] = True
    if sys.argv[1] == 'test':
        _ = Path('/scratch/result').write_text('synthetic test result\n')
        checks['separate_scratch'] = Path('/scratch/result').read_text() == 'synthetic test result\n'
    else:
        checks['scratch_absent'] = not Path('/scratch').exists()
    try:
        with socket.create_connection(('192.0.2.1', 443), timeout=1):
            checks['network_denied'] = False
    except OSError as error:
        checks['network_denied'] = error.errno in (1, 13, 101)
    print(json.dumps(checks, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
