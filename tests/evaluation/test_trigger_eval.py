"""Post-run trigger classification (S2.1, design §5.4)."""

from __future__ import annotations

from datetime import UTC, datetime

from helios.evaluation.trigger_eval import (
    TriggerLabel,
    classify_trigger,
    injection_inside_window,
    trigger_delay_s,
)
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.trigger import TriggerRecord, TriggerSource
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

T0 = 1_790_000_000


def _rec(at: float, source: TriggerSource = TriggerSource.THRESHOLD) -> TriggerRecord:
    return TriggerRecord(
        incident_id="x",
        trigger_time_s=at,
        suspects=("cart",),
        context=(),
        source=source,
        detector_hash="d" * 64,
    )


def test_threshold_trigger_before_the_fault_is_false() -> None:
    assert classify_trigger(_rec(T0 + 100), T0 + 300) == TriggerLabel.FALSE


def test_threshold_trigger_at_or_after_the_fault_is_true() -> None:
    assert classify_trigger(_rec(T0 + 300), T0 + 300) == TriggerLabel.TRUE
    assert classify_trigger(_rec(T0 + 330), T0 + 300) == TriggerLabel.TRUE


def test_fallback_is_no_trigger_whenever_it_lands() -> None:
    assert (
        classify_trigger(_rec(T0 + 330, TriggerSource.FALLBACK), T0 + 300)
        == TriggerLabel.NO_TRIGGER
    )


def test_delay_only_for_true_triggers() -> None:
    assert trigger_delay_s(_rec(T0 + 330), T0 + 300) == 30
    assert trigger_delay_s(_rec(T0 + 100), T0 + 300) is None
    assert trigger_delay_s(_rec(T0 + 330, TriggerSource.FALLBACK), T0 + 300) is None


def test_injection_inside_window() -> None:
    window = TelemetryWindow(
        incident_id="x",
        variant_config_hash="h" * 64,
        window_start_iso=datetime.fromtimestamp(T0, UTC).isoformat(),
        window_end_iso=datetime.fromtimestamp(T0 + 600, UTC).isoformat(),
        evaluation_phase=EvaluationPhase.EXPLORATORY,
    )
    assert injection_inside_window(window, T0 + 300)
    assert not injection_inside_window(window, T0 - 1)
    assert not injection_inside_window(window, T0 + 601)
