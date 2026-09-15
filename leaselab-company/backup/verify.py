"""Validate a native archive without restoring into any live Hermes home."""
import sqlite3
import stat
import sys
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath


def verify(archive: Path) -> None:
    """Check CRC, archive paths, required state and every SQLite snapshot."""
    with zipfile.ZipFile(archive) as bundle, tempfile.TemporaryDirectory() as scratch:
        if bundle.testzip() is not None:
            raise RuntimeError("Archive CRC verification failed")
        required = {"kanban.db", "shared-state.db"}
        for profile in ("chief-of-staff", "engineer", "qa-security", "reviewer", "sre", "support", "growth"):
            required.update(f"profiles/{profile}/{name}" for name in ("state.db", "config.yaml", "SOUL.md"))
        if not required.issubset(bundle.namelist()):
            raise RuntimeError("Archive is missing required company state")
        for index, entry in enumerate(bundle.infolist()):
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename:
                raise RuntimeError("Unsafe archive path")
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise RuntimeError("Archive symlink refused")
            # Native external-provider backup must not widen coverage to role credential homes.
            if path.parts and path.parts[0] == "_external":
                raise RuntimeError("External provider state requires an explicit backup policy")
            if entry.filename.endswith((".db-wal", ".db-shm", ".db-journal")):
                raise RuntimeError("SQLite sidecar in archive")
            if path.suffix in (".db", ".sqlite"):
                destination = Path(scratch) / f"{index}.db"
                destination.write_bytes(bundle.read(entry))
                with closing(sqlite3.connect(f"{destination.as_uri()}?mode=ro", uri=True)) as database:
                    if database.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                        raise RuntimeError("SQLite integrity verification failed")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
    print("Native archive CRC and SQLite integrity: PASS")
