# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# Run: /usr/bin/python3 patch-context-permissions.py --check|--apply
"""Reversible permission-safe context discovery patch for verified Hermes source."""

import hashlib
import os
import socket
import sys
import tempfile
from pathlib import Path
from typing import Final

TARGET: Final = Path("/home/hermes/.hermes/hermes-agent/agent/prompt_builder.py")
BACKUP: Final = Path("/var/backups/leaselab-company/native-context-permissions")
ORIGINAL_SHA: Final = "586ea363fa1e70bb0fdd5426af40758976a16c54f07efeb7a1b4f3fe0ad99309"
OLD: Final = """        sections = [_load_hermes_md(cwd_path, context_length) or _load_agents_md(cwd_path, context_length)
                    or _load_claude_md(cwd_path, context_length) or _load_cursorrules(cwd_path, context_length)]"""
NEW: Final = """        try:
            sections = [_load_hermes_md(cwd_path, context_length) or _load_agents_md(cwd_path, context_length)
                        or _load_claude_md(cwd_path, context_length) or _load_cursorrules(cwd_path, context_length)]
        except PermissionError:
            # Remote SSH workspaces may be inaccessible to the central prompt-building UID.
            # Keep SOUL loading below independent; never broaden role filesystem permissions.
            logger.warning("Local project context inaccessible; preserving profile identity")
            sections = []"""


def patched_source(source: bytes) -> bytes:
    """Accept only the verified original or this exact idempotent patch."""
    text = source.decode("utf-8")
    original = text.replace(NEW, OLD) if text.count(NEW) == 1 else text
    if (
        hashlib.sha256(original.encode()).hexdigest() != ORIGINAL_SHA
        or original.count(OLD) != 1
    ):
        raise RuntimeError(
            "Hermes context source drift; inspect current upstream before patching"
        )
    return original.replace(OLD, NEW).encode()


def main() -> int:
    if sys.argv[1:] not in (["--check"], ["--apply"]):
        print("Usage: patch-context-permissions.py --check|--apply")
        return 64
    source = TARGET.read_bytes()
    desired = patched_source(source)
    if sys.argv[1] == "--apply" and source != desired:
        if os.geteuid() != 0 or socket.gethostname() != "hermes-leaselab":
            raise RuntimeError("Apply requires root on hermes-leaselab")
        BACKUP.mkdir(parents=True, mode=0o700, exist_ok=True)
        original = BACKUP / (ORIGINAL_SHA + ".py")
        if (
            original.exists()
            and hashlib.sha256(original.read_bytes()).hexdigest() != ORIGINAL_SHA
        ):
            raise RuntimeError("Context patch backup integrity mismatch")
        if not original.exists():
            _ = original.write_bytes(source)
            original.chmod(0o600)
        info = TARGET.stat()
        descriptor, temporary = tempfile.mkstemp(
            prefix=".context-patch-", dir=TARGET.parent
        )
        path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), info.st_mode & 0o777)
                os.fchown(handle.fileno(), info.st_uid, info.st_gid)
                _ = handle.write(desired)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(path, TARGET)
        finally:
            path.unlink(missing_ok=True)
    print(
        "Context permission patch verified; original="
        + ORIGINAL_SHA
        + "; patched="
        + hashlib.sha256(desired).hexdigest()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
