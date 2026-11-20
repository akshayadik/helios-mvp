from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from helios.telemetry import pool_lock
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterator

TEST_LOCK_REASON = "tests: the pool is locked for this repository (tests/conftest.py)"


@pytest.fixture(autouse=True)
def _pool_locked_for_this_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep the confirmatory pool locked for this checkout in every test.

    The gates ask about this repository by default, and once tag build-freeze
    exists a clean checkout of it is the frozen build, so a test would see the
    pool open or shut depending on the tags in its clone. Here the default
    root always reads as locked; tests that need it open patch the gate
    themselves, and the freeze tests build their own repositories, which
    still get the real check (tests/test_build_freeze.py).
    """
    real = pool_lock.lock_reasons
    own_root = Path(pool_lock._REPO_ROOT).resolve()

    def reasons(repo_root: Path = own_root) -> list[str]:
        if Path(repo_root).resolve() == own_root:
            return [TEST_LOCK_REASON]
        return real(repo_root)

    monkeypatch.setattr(pool_lock, "lock_reasons", reasons)
    yield
