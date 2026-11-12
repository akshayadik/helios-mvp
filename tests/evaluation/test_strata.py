"""Narrative-heavy stratum (A-H6; S4.9 M-e): hand-computed fixtures."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pandas as pd
import pytest

from helios.evaluation import strata
from helios.evaluation.strata import (
    STRATUM_VERSION,
    NoveltyShare,
    inject_unix,
    is_narrative_heavy,
    load_inject_times,
    load_tau,
    median_tau,
    narrative_heavy_by_incident,
    novelty_share,
    tau_params_hash,
)
from helios.telemetry.log_templates import extract_templates, line_templates
from helios.telemetry.pool_lock import PoolLockedError
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

INJECT = 1_700_000_600  # Unix seconds; the window runs from INJECT - 600 s
BASE = pd.Timestamp(INJECT - 600, unit="s", tz="UTC")

KNOWN = "user login accepted for account {n}"  # one template, seen before injection
NEW = "payment gateway timeout after retry {n} on route checkout"  # post only


def _logs(rows: list[tuple[int, str, str]]) -> pd.DataFrame:
    """Rows of (seconds after BASE, service, body) as P3 log rows."""
    return pd.DataFrame(
        {
            "timestamp": [
                (BASE + pd.Timedelta(seconds=s)).isoformat() for s, _, _ in rows
            ],
            "service_name": [svc for _, svc, _ in rows],
            "body": [body for _, _, body in rows],
        }
    )


def test_share_counts_post_lines_whose_template_is_new() -> None:
    # Pre: KNOWN twice. Post: KNOWN once, NEW three times -> 3 novel of 4 post.
    logs = _logs(
        [
            (10, "front", KNOWN.format(n=1)),
            (20, "front", KNOWN.format(n=2)),
            (610, "front", KNOWN.format(n=3)),
            (620, "pay", NEW.format(n=1)),
            (630, "pay", NEW.format(n=2)),
            (640, "pay", NEW.format(n=3)),
        ]
    )
    counts = novelty_share(logs, INJECT)
    assert counts == NoveltyShare(
        pre_lines=2, post_lines=4, novel_post_lines=3, novel_post_templates=1
    )
    assert counts.share == pytest.approx(3 / 4)


def test_seen_is_window_wide_not_per_service() -> None:
    # KNOWN is emitted pre-injection by "front"; "cart" emitting it later is not novel.
    logs = _logs([(10, "front", KNOWN.format(n=1)), (650, "cart", KNOWN.format(n=2))])
    counts = novelty_share(logs, INJECT)
    assert counts is not None
    assert counts.novel_post_lines == 0
    assert counts.share == 0


def test_line_at_injection_time_is_post_injection() -> None:
    logs = _logs([(10, "front", KNOWN.format(n=1)), (600, "pay", NEW.format(n=1))])
    counts = novelty_share(logs, INJECT)
    assert counts is not None
    assert (counts.pre_lines, counts.post_lines, counts.novel_post_lines) == (1, 1, 1)


def test_no_post_injection_lines_has_no_share() -> None:
    counts = novelty_share(_logs([(10, "front", KNOWN.format(n=1))]), INJECT)
    assert counts is not None
    assert counts.share is None


def test_no_pre_injection_lines_makes_every_post_line_novel() -> None:
    logs = _logs([(610, "front", KNOWN.format(n=1)), (620, "pay", NEW.format(n=1))])
    counts = novelty_share(logs, INJECT)
    assert counts is not None
    assert counts.pre_lines == 0
    assert counts.novel_post_lines == counts.post_lines == 2


def test_empty_or_unusable_logs_give_none() -> None:
    assert novelty_share(_logs([]), INJECT) is None
    blank = pd.DataFrame(
        {"timestamp": ["not a time"], "service_name": ["a"], "body": ["x"]}
    )
    assert novelty_share(blank, INJECT) is None


def test_row_order_does_not_change_the_share() -> None:
    rows = [
        (10, "front", KNOWN.format(n=1)),
        (620, "pay", NEW.format(n=1)),
        (630, "front", KNOWN.format(n=2)),
    ]
    forward = novelty_share(_logs(rows), INJECT)
    backward = novelty_share(_logs(rows[::-1]), INJECT)
    assert forward == backward


def test_line_templates_matches_extract_templates() -> None:
    # One Drain pass for both: template counts agree with the S1.4 features.
    logs = _logs([(10, "a", KNOWN.format(n=1)), (20, "b", NEW.format(n=2))])
    frame, skipped = line_templates(logs)
    features = extract_templates(logs, BASE.isoformat())
    assert skipped == features.skipped_lines == 0
    assert sorted(frame["template_id"]) == sorted(features.counts["template_id"])


def test_inject_unix_accepts_numbers_and_iso() -> None:
    assert inject_unix(INJECT) == float(INJECT)
    iso = pd.Timestamp(INJECT, unit="s", tz="UTC").isoformat()
    assert inject_unix(iso) == float(INJECT)
    naive = pd.Timestamp(INJECT, unit="s").isoformat()
    assert inject_unix(naive) == float(INJECT)
    with pytest.raises(TypeError):
        inject_unix(True)
    with pytest.raises(TypeError):
        inject_unix(None)


def test_median_tau_ignores_missing_shares_and_averages_the_middle_pair() -> None:
    assert median_tau([0.2, None, 0.3, 0.6, 0.8]) == pytest.approx(0.45)
    assert median_tau([0.1, 0.3, 0.9]) == pytest.approx(0.3)
    with pytest.raises(ValueError, match="at least one"):
        median_tau([None])


def test_stratum_is_at_or_above_tau() -> None:
    assert is_narrative_heavy(0.3, 0.3) is True
    assert is_narrative_heavy(0.29, 0.3) is False
    assert is_narrative_heavy(None, 0.3) is None
    flags = narrative_heavy_by_incident({"a": 0.4, "b": 0.1, "c": None}, 0.3)
    assert flags == {"a": True, "b": False}


def test_inject_times_respect_the_pool_lock(tmp_path: Path) -> None:
    with pytest.raises(PoolLockedError):
        load_inject_times("pool", root=tmp_path, key=b"k", frozen=lambda: False)
    with pytest.raises(ValueError, match="no injection time"):
        load_inject_times("captures", root=tmp_path, key=b"k")


def test_inject_times_read_the_signed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases: dict[str, dict[str, Any]] = {
        "c1": {"inject_time": INJECT},
        "c2": {"inject_time": pd.Timestamp(INJECT, unit="s", tz="UTC").isoformat()},
    }
    seen: list[Path] = []

    def verify(path: Path, key: bytes) -> dict[str, dict[str, Any]]:
        seen.append(path)
        assert key == b"k"
        return cases

    monkeypatch.setattr(strata, "verify_ground_truth", verify)
    times = load_inject_times("build", root=tmp_path, key=b"k")
    assert times == {"c1": float(INJECT), "c2": float(INJECT)}
    assert seen == [tmp_path / "data/rcaeval/ground_truth_build.json"]


def test_load_tau(tmp_path: Path) -> None:
    path = tmp_path / "tau.json"
    assert load_tau(tmp_path, path) is None
    path.write_text(json.dumps({"version": STRATUM_VERSION, "tau_n": 0.25}))
    assert load_tau(tmp_path, path) == pytest.approx(0.25)
    path.write_text(json.dumps({"version": "other", "tau_n": 0.25}))
    with pytest.raises(ValueError, match="version"):
        load_tau(tmp_path, path)


def test_tau_params_hash_is_stable_and_order_free() -> None:
    a = tau_params_hash({"tau_n": 0.25, "version": STRATUM_VERSION})
    b = tau_params_hash({"version": STRATUM_VERSION, "tau_n": 0.25})
    assert a == b
    assert len(a) == 12


def test_committed_tau_matches_its_fit_report() -> None:
    import hashlib
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    report = (
        root / "docs/sprints/s4-product-eval-tooling/calibration/narrative_share.json"
    )
    frozen = json.loads((root / strata.TAU_PATH).read_text(encoding="utf-8"))
    assert load_tau(root) == json.loads(report.read_text(encoding="utf-8"))["tau_n"]
    assert frozen["report_sha256"] == hashlib.sha256(report.read_bytes()).hexdigest()
    assert tau_params_hash(frozen) == "571509dd4ba7"
