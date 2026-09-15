"""Root-only synthetic positive/negative test of the same auth-free command."""
import fcntl
import json
import os
import pwd
import secrets

from executor_capture import capture
from executor_config import executor
from publisher_models import Denied
from verification_run import ROOT, policy_file, test_command


def main() -> None:
    if os.geteuid() != 0:
        raise Denied
    selected = executor('qa-security')
    account = pwd.getpwnam(selected.user)
    with (selected.root / 'lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for text, expected in (('# Harmless fixture\n', 0), ('<<<<<<< seeded defect\n', 2)):
            evidence = ROOT / 'evidence' / secrets.token_hex(32)
            evidence.mkdir(mode=0o700)
            fixture_root = ROOT / 'verification-fixtures'
            fixture_root.mkdir(mode=0o755, exist_ok=True)
            fixture_root.chmod(0o755)
            source = fixture_root / evidence.name
            source.mkdir(mode=0o755, parents=True)
            (source / 'head').mkdir(mode=0o755)
            (source / 'base').mkdir(mode=0o555)
            (source / 'head/docs').mkdir(mode=0o755)
            document = source / 'head/docs/sample.md'
            _ = document.write_text(text)
            document.chmod(0o444)
            (source / 'head/docs').chmod(0o555)
            (source / 'head').chmod(0o555)
            source.chmod(0o555)
            recipe = policy_file(('docs/sample.md',), evidence.name)
            scratch = selected.root / 'work' / evidence.name
            scratch.mkdir(mode=0o700)
            os.chown(scratch, account.pw_uid, account.pw_gid)
            result = capture(test_command(source, recipe, scratch), evidence / 'test-output', timeout=30, maximum=65536)
            report = {'fixture': True, 'job': evidence.name, 'expected_exit': expected,
                      'actual_exit': result.exit_code, 'limited': result.limited, 'digest': result.digest}
            payload = json.dumps(report, sort_keys=True)
            _ = (evidence / 'fixture.json').write_text(payload)
            (evidence / 'fixture.json').chmod(0o400)
            print(payload)
            if result.limited or result.exit_code != expected:
                raise Denied


if __name__ == '__main__':
    main()
