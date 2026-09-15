"""Verified source patch is bounded, idempotent and refuses upstream drift."""

import hashlib
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "context_patch",
    Path(__file__).parents[1] / "bootstrap" / "patch-context-permissions.py",
)
assert SPEC and SPEC.loader
patch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch)


def test_patch_is_idempotent_and_preserves_surrounding_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = ("before\n" + patch.OLD + "\nafter").encode()
    monkeypatch.setattr(patch, "ORIGINAL_SHA", hashlib.sha256(source).hexdigest())
    result = patch.patched_source(source)
    assert result == ("before\n" + patch.NEW + "\nafter").encode()
    assert patch.patched_source(result) == result
    with pytest.raises(RuntimeError, match="drift"):
        patch.patched_source(source + b"\n")
