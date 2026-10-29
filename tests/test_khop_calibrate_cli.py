"""bin/khop_calibrate.py: the OTel v3 build corpus (S2.2 carry-over)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def test_otel_build_v3_corpus_reads_its_signed_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bin import khop_calibrate

    seen: list[Path] = []

    def verify(path: Path, key: bytes) -> dict[str, dict[str, str]]:
        seen.append(path)
        return {"c1": {"root_cause_service": "payment"}}

    monkeypatch.setattr(khop_calibrate, "verify_ground_truth", verify)
    monkeypatch.setattr(khop_calibrate, "load_key", lambda: b"k")
    base, order, labels = khop_calibrate._cases("otel_build_v3", None)
    manifest = json.loads(
        (REPO / "data/otel/build_v3_manifest.json").read_text(encoding="utf-8")
    )
    assert base == REPO / "data/otel/build_v3"
    assert order == manifest["case_order"]
    assert len(order) == 63
    assert seen == [REPO / "data/otel/ground_truth_build_v3.json"]
    assert labels == {"c1": "payment"}
