"""Bounded supervisor capture checks using synthetic subprocesses only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authority/publisher'))
from executor_capture import capture


def test_capture_seals_output(tmp_path: Path) -> None:
    target = tmp_path / 'output'
    result = capture([sys.executable, '-c', 'print("synthetic")'], target)
    assert result.exit_code == 0
    assert not result.limited
    assert target.read_bytes() == b'synthetic\n'
    assert target.stat().st_mode & 0o777 == 0o400


def test_capture_bounded_output(tmp_path: Path) -> None:
    target = tmp_path / 'output'
    result = capture([sys.executable, '-c', 'import os;os.write(1,b"x"*10000)'], target, maximum=32)
    assert result.limited
    assert target.stat().st_size <= 32


def test_capture_timeout(tmp_path: Path) -> None:
    result = capture([sys.executable, '-c', 'import time;time.sleep(20)'], tmp_path / 'output', timeout=0.1)
    assert result.limited
    assert result.exit_code != 0


def test_capture_does_not_replace(tmp_path: Path) -> None:
    import pytest
    target = tmp_path / 'output'
    target.write_text('existing')
    with pytest.raises(FileExistsError):
        capture([sys.executable, '-c', 'print(1)'], target)
    assert target.read_text() == 'existing'
