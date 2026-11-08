"""bin/otel_fix_validate.py (entry 76 O-f); never runs on v4 here."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _hits(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    from bin.otel_fix_validate import DECISION

    return {"old": {DECISION: old}, "new": {DECISION: new}}


def _r(v4: int, rca: float) -> dict[str, Any]:
    return {
        "otel_heldout_v4": {"hits": v4, "hr_at_3": v4 / 36},
        "rcaeval_build": {"hr_at_3": rca},
    }


@pytest.mark.parametrize(
    ("old", "new", "adopted"),
    [
        (_r(28, 0.97), _r(30, 0.97), True),  # +2 on v4, RCAEval equal
        (_r(28, 0.97), _r(29, 0.98), False),  # +1 is not enough
        (_r(28, 0.97), _r(31, 0.96), False),  # RCAEval lower
    ],
)
def test_the_rule_needs_two_more_v4_cases_and_no_rcaeval_loss(
    old: dict[str, Any], new: dict[str, Any], adopted: bool
) -> None:
    from bin.otel_fix_validate import decide

    assert decide(_hits(old, new))["adopted"] is adopted


def test_v4_is_read_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from bin import otel_fix_validate

    (tmp_path / otel_fix_validate.REPORT).parent.mkdir(parents=True)
    (tmp_path / otel_fix_validate.REPORT).write_text("{}")
    monkeypatch.setattr(otel_fix_validate, "REPO_ROOT", tmp_path)
    assert otel_fix_validate.main([]) == 2
    assert "read once" in capsys.readouterr().err


def test_an_incomplete_candidate_is_refused(tmp_path: Path) -> None:
    from bin.otel_fix_validate import chains

    with pytest.raises(FileNotFoundError, match="lacks"):
        chains(tmp_path)


def test_the_otel_fix_candidate_is_complete_and_differs_from_frozen() -> None:
    from bin.otel_fix_validate import chains

    sets = chains()
    old, new = sets["old"][0].hashes(), sets["new"][0].hashes()
    assert old["dpipe"] == new["dpipe"]  # fix B dropped (entry 77)
    assert old["gpipe"] != new["gpipe"] and old["mahc"] != new["mahc"]
