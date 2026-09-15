"""Root supervision of the fixed Reviewer lane, without publishing approval."""
import fcntl
import hashlib
import os
from pathlib import Path

from executor_capture import capture
from executor_config import executor
from publisher_models import Denied
from review_events import disposition
from review_launch import launch
from review_models import ReviewIdentity


def review(source: Path, identity: ReviewIdentity, paths: tuple[str, ...], evidence: Path, *, fixture: bool = False) -> str:
    selected = executor('reviewer')
    with (selected.root / 'lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        preflight, inference = launch(source, identity, paths, fixture=fixture)
        check = capture(preflight, evidence / 'review-boundary-output', timeout=30, maximum=16384)
        if check.exit_code != 0 or check.limited:
            raise Denied
        result = capture(inference, evidence / 'review-events', timeout=180, maximum=1048576)
        if result.exit_code != 0 or result.limited:
            raise Denied
        semantic = disposition((evidence / 'review-events').read_bytes(), identity, paths)
        for finding in semantic.disposition.findings:
            if finding.line > len((source / 'head' / finding.path).read_text().splitlines()):
                raise Denied
        raw = semantic.model_dump_json().encode()
        with (evidence / 'review-disposition.json').open('xb') as output:
            _ = output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        (evidence / 'review-disposition.json').chmod(0o400)
        return hashlib.sha256(raw).hexdigest()
