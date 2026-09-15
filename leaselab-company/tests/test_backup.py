"""Backup policy fixtures; no live deployment or transport is performed."""
import importlib.util
import shutil
import sqlite3
import subprocess
import zipfile
from pathlib import Path

import pytest

BACKUP = Path(__file__).resolve().parents[1] / "backup"
PROFILES = ("chief-of-staff", "engineer", "qa-security", "reviewer", "sre", "support", "growth")


def test_native_archive_integrity_and_path_guards(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("backup_verify", BACKUP / "verify.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE sample (value TEXT)")
        database.execute("INSERT INTO sample VALUES ('durable')")
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in ("kanban.db", "shared-state.db"):
            bundle.write(source, name)
        for profile in PROFILES:
            bundle.write(source, f"profiles/{profile}/state.db")
            bundle.writestr(f"profiles/{profile}/config.yaml", "model: fixture\n")
            bundle.writestr(f"profiles/{profile}/SOUL.md", "Fixture\n")
    module.verify(archive)
    for unsafe in ("../escape.db", "_external/.codex/auth.json", "profiles/engineer/state.db-wal"):
        rejected = tmp_path / "rejected.zip"
        shutil.copyfile(archive, rejected)
        with zipfile.ZipFile(rejected, "a") as bundle:
            bundle.writestr(unsafe, "fixture")
        with pytest.raises(RuntimeError):
            module.verify(rejected)
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("corrupt.db", "broken database")
    with pytest.raises(sqlite3.DatabaseError):
        module.verify(archive)
    assert not (tmp_path / "escape.db").exists()


def test_candidate_allowlist_and_secret_failure(tmp_path: Path) -> None:
    if not shutil.which("gitleaks"):
        pytest.skip("Requires deployed gitleaks and Linux realpath for production shell fixture")
    source = tmp_path / "company"
    for profile in PROFILES:
        home = source / "profiles" / profile
        home.mkdir(parents=True)
        (home / "SOUL.md").write_text("Durable instructions\n")
        (home / "config.yaml").write_text("model: fixture\n")
        (home / ".env").write_text("DO_NOT_COPY=fixture\n")
        (home / "state.db").write_text("DO_NOT_COPY\n")
        (home / "skills").mkdir()
        (home / "skills" / "notes.md").write_text("Durable skill\n")
        (home / "skills" / "auth.json").write_text("DO_NOT_COPY\n")
    candidate = tmp_path / "candidate"
    command = ["bash", str(BACKUP / "candidate.sh"), str(source), str(candidate)]
    subprocess.run(command, check=True, capture_output=True)
    assert (candidate / "profiles/engineer/config.yaml").is_file()
    assert (candidate / "profiles/engineer/skills/notes.md").is_file()
    assert not list(candidate.rglob(".env"))
    assert not list(candidate.rglob("*.db"))
    assert not list(candidate.rglob("auth.json"))
    command[-1] = str(tmp_path / "secret-candidate")
    # Synthetic scanner fixture assembled at runtime; never an actual credential.
    (source / "profiles/engineer/skills/notes.md").write_text("github_token = ghp_" + "aB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV3wX4" + "\n")
    assert subprocess.run(command, capture_output=True).returncode != 0
    command[-1] = str(source / "forbidden")
    assert subprocess.run(command, capture_output=True).returncode != 0
    assert not (source / "forbidden").exists()
