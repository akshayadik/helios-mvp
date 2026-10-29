"""Trigger calibration (S2.1, design §5.3): evaluation, selection rule, audit."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from helios.evaluation.trigger_calibration import (
    CROP_FRACTIONS,
    GRID,
    CalibrationCase,
    CorpusResult,
    audit_passes,
    crop_starts,
    evaluate,
    select,
)
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.trigger import (
    WARMUP_BUCKETS,
    DetectorParams,
    TriggerRecord,
    TriggerSource,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

T0 = 1_790_000_000


def _case(
    i: int, inject: float = T0 + 600, fault: str | None = None
) -> CalibrationCase:
    window = TelemetryWindow(
        incident_id=f"c{i}",
        variant_config_hash="h" * 64,
        window_start_iso=datetime.fromtimestamp(T0, UTC).isoformat(),
        window_end_iso=datetime.fromtimestamp(T0 + 1200, UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
    )
    return CalibrationCase(
        incident_id=f"c{i}",
        window=window,
        inject_time_s=inject,
        root_cause="cart",
        fault=fault,
    )


def _rec(
    i: int,
    at: float,
    *,
    source: TriggerSource = TriggerSource.THRESHOLD,
    suspects: tuple[str, ...] = ("cart",),
) -> TriggerRecord:
    return TriggerRecord(
        incident_id=f"c{i}",
        trigger_time_s=at,
        suspects=suspects,
        context=(),
        source=source,
        detector_hash="d" * 64,
    )


def _result(
    false: int, n: int = 20, delay: float | None = 30, no: int = 0
) -> CorpusResult:
    return CorpusResult(
        n=n,
        true=n - false - no,
        false=false,
        no_trigger=no,
        excluded=0,
        median_delay_s=delay,
        root_among_suspects=0,
        false_by_fault={},
    )


# ── evaluation ───────────────────────────────────────────────────────────────


def test_evaluate_counts_labels_delay_and_suspect_hits() -> None:
    cases = [_case(0), _case(1), _case(2, fault="adFailure")]
    records = [
        _rec(0, T0 + 630),
        _rec(1, T0 + 300, suspects=("ad",)),
        _rec(2, T0 + 700, source=TriggerSource.FALLBACK),
    ]
    result = evaluate(records, cases)
    assert (result.true, result.false, result.no_trigger, result.n) == (1, 1, 1, 3)
    assert result.median_delay_s == 30
    assert result.root_among_suspects == 2
    assert result.false_rate == pytest.approx(1 / 3)
    assert result.false_by_fault == {"adFailure": 0}


def test_evaluate_excludes_injections_outside_the_window() -> None:
    cases = [_case(0), _case(1, inject=T0 - 50)]
    result = evaluate([_rec(0, T0 + 630), _rec(1, T0 + 630)], cases)
    assert (result.n, result.excluded) == (1, 1)


# ── selection rule ───────────────────────────────────────────────────────────


def test_select_requires_five_percent_on_each_corpus() -> None:
    ok, bad = DetectorParams(30, 6, 2, False), DetectorParams(30, 4, 1, False)
    results = {
        ok: {"rcaeval_build": _result(1, delay=60), "otel_build": _result(1, delay=60)},
        bad: {
            "rcaeval_build": _result(0, delay=10),
            "otel_build": _result(2, delay=10),
        },
    }
    assert select(results) == ok  # bad has 10% false on OTel, despite a shorter delay


def test_select_prefers_shorter_delay_then_fewer_misses_then_higher_threshold() -> None:
    a, b, c = (
        DetectorParams(30, 6, 2, False),
        DetectorParams(30, 8, 2, False),
        DetectorParams(30, 5, 2, False),
    )
    tie = {"rcaeval_build": _result(0, delay=30), "otel_build": _result(0, delay=30)}
    fewer_misses = {
        "rcaeval_build": _result(0, delay=30, no=0),
        "otel_build": _result(0, delay=30, no=0),
    }
    more_misses = {
        "rcaeval_build": _result(0, delay=30, no=2),
        "otel_build": _result(0, delay=30, no=0),
    }
    assert select({a: tie, b: tie}) == b  # same delay and misses: higher threshold
    assert select({a: fewer_misses, c: more_misses}) == a
    faster = {"rcaeval_build": _result(0, delay=10), "otel_build": _result(0, delay=20)}
    assert select({a: tie, c: faster}) == c


def test_select_returns_none_when_nothing_qualifies() -> None:
    p = DetectorParams(30, 6, 2, False)
    assert select({p: {"rcaeval_build": _result(5), "otel_build": _result(0)}}) is None
    no_true = {"rcaeval_build": _result(0, delay=None), "otel_build": _result(0)}
    assert select({p: no_true}) is None


# ── crop-invariance audit ────────────────────────────────────────────────────


def test_crops_use_only_the_slack_beyond_warmup_and_persistence() -> None:
    case = _case(0, inject=T0 + 600)
    slack = 600 - (WARMUP_BUCKETS + max(GRID["persistence"]) + 1) * 30
    assert crop_starts(case, 30) == [round(f * slack, 6) for f in CROP_FRACTIONS]
    tight = _case(1, inject=T0 + 120)
    assert crop_starts(tight, 30) == []


def test_audit_fails_when_a_crop_raises_false_triggers_or_moves_delay() -> None:
    base = _result(0, delay=30)
    assert audit_passes(base, {0.25: _result(1, delay=30)}, bucket_seconds=30)
    assert not audit_passes(base, {0.25: _result(2, delay=30)}, bucket_seconds=30)
    assert not audit_passes(base, {0.25: _result(0, delay=90)}, bucket_seconds=30)


def test_calibration_cli_refuses_pool() -> None:
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "bin/trigger_calibrate.py", "--corpus", "pool"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "pool" in result.stderr


def test_calibration_uses_a_fixed_sixty_second_onset_tolerance() -> None:
    from helios.evaluation.trigger_calibration import ONSET_TOLERANCE_S

    assert ONSET_TOLERANCE_S == 60
    cases = [_case(0, inject=T0 + 620)]
    # 30 s bucket [540, 570) ends 50 s before the injection: within tolerance.
    assert evaluate([_rec(0, T0 + 540)], cases, bucket_seconds=30).false == 0
    # bucket [480, 510) ends 110 s before: false.
    assert evaluate([_rec(0, T0 + 480)], cases, bucket_seconds=30).false == 1


def test_untolerated_false_count_is_reported_beside() -> None:
    cases = [_case(0, inject=T0 + 620)]
    result = evaluate([_rec(0, T0 + 540)], cases, bucket_seconds=30)
    assert (result.false, result.false_untolerated) == (0, 1)
    assert result.as_dict()["false_untolerated"] == 1


def test_calibration_uses_rcaeval_build_and_otel_build_v3() -> None:
    # Deviation entry 50: v3 replaces v2 for OTel (attributed logs, span
    # metrics, 25 users); v2 stays committed with calibration runs 4 and 5.
    from helios.evaluation.trigger_calibration import CORPORA

    assert list(CORPORA) == ["rcaeval_build", "otel_build_v3"]
    assert CORPORA["otel_build_v3"] == (
        "data/otel/build_v3",
        "data/otel/build_v3_manifest.json",
        "data/otel/ground_truth_build_v3.json",
    )


def test_otel_v3_cases_carry_their_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from helios.evaluation import trigger_calibration as tc

    captures = tmp_path / "data/otel/build_v3/c0"
    captures.mkdir(parents=True)
    window = _case(0).window.model_dump(mode="json")
    (captures / "manifest.json").write_text(json.dumps(window), encoding="utf-8")
    (tmp_path / "data/otel/build_v3_manifest.json").write_text(
        json.dumps({"case_order": ["c0"]}), encoding="utf-8"
    )
    label = {"inject_time": T0 + 600, "root_cause_service": "ad", "fault": "adFailure"}
    monkeypatch.setattr(tc, "verify_ground_truth", lambda _p, _k: {"c0": label})
    cases = tc.load_cases("otel_build_v3", root=tmp_path, key=b"k")
    assert cases[0].fault == "adFailure"
