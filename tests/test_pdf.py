"""PDF engine helpers — no actual rendering."""

import os

import pytest

from still.render.pdf import _weasyprint_env


def test_weasyprint_env_preserves_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Injecting the Homebrew libdir must never clobber a caller-set path."""
    monkeypatch.setenv("DYLD_FALLBACK_LIBRARY_PATH", "/custom/lib")
    env = _weasyprint_env()
    parts = env["DYLD_FALLBACK_LIBRARY_PATH"].split(os.pathsep)
    assert "/custom/lib" in parts
    # no duplicate entries when re-invoked
    assert len(parts) == len(set(parts))
