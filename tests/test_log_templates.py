"""Tests for Drain3 log templates and window features (S1.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.log_templates import (
    LogTemplateFeatures,
    extract_templates,
    features_for_window,
    template_id,
)
from helios.telemetry.pool_lock import PoolLockedError
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

START = "2026-10-25T10:00:00Z"


def _logs(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["timestamp", "service_name", "body"])


def _sample() -> pd.DataFrame:
    rows = []
    for i in range(6):
        rows.append(
            (f"2026-10-25T10:00:{i:02d}Z", "carts", f"GET /cart/{i} took {i + 3} ms")
        )
        rows.append((f"2026-10-25T10:00:{i:02d}Z", "orders", f"order {i + 7} accepted"))
    for i in range(4):
        rows.append(
            (
                f"2026-10-25T10:01:{i:02d}Z",
                "carts",
                f"connection to 10.0.3.{i}:5432 refused",
            )
        )
    rows.append(("2026-10-25T10:01:10Z", "orders", "   "))
    rows.append(("not a time", "orders", "order 9 accepted"))
    return _logs(rows)


def _by_template(features: LogTemplateFeatures) -> dict[str, int]:
    return dict(
        zip(features.templates["template"], features.templates["count"], strict=False)
    )


def test_messages_collapse_to_masked_templates() -> None:
    features = extract_templates(_sample(), START)
    assert _by_template(features) == {
        "GET /cart/<NUM> took <NUM> ms": 6,
        "order <NUM> accepted": 6,
        "connection to <IP> refused": 4,
    }
    assert features.skipped_lines == 2


def test_timestamps_emails_and_durations_are_masked() -> None:
    rows = [
        (
            f"2026-10-25T10:00:0{i}Z",
            "user",
            f"ts=2024-11-24T12:3{i}:19.44072{i}Z method=Register "
            f"email=u{i}x@example.com took=1.8{i}ms",
        )
        for i in range(3)
    ]
    features = extract_templates(_logs(rows), START)
    assert features.templates["template"].tolist() == [
        "ts=<TIME> method=Register email=<EMAIL> took=<DUR>"
    ]


def test_template_ids_are_content_hashes() -> None:
    features = extract_templates(_sample(), START)
    for tid, text in zip(
        features.templates["template_id"], features.templates["template"], strict=False
    ):
        assert tid == template_id(text)
    assert template_id("order <NUM> accepted") == template_id("order <NUM> accepted")
    assert len(template_id("x")) == 12


def test_counts_are_bucketed_per_service_from_the_window_start() -> None:
    features = extract_templates(_sample(), START, bucket_seconds=30)
    counts = features.counts
    assert set(counts["bucket_start"]) == {
        "2026-10-25T10:00:00Z",
        "2026-10-25T10:01:00Z",
    }
    carts_late = counts[
        (counts["service"] == "carts")
        & (counts["bucket_start"] == "2026-10-25T10:01:00Z")
    ]
    assert carts_late["count"].tolist() == [4]
    assert int(counts["count"].sum()) == 16


def test_novelty_marks_first_appearance_per_service() -> None:
    features = extract_templates(_sample(), START, bucket_seconds=30)
    novelty = features.novelty.set_index(["bucket_start", "service"])
    assert novelty.loc[("2026-10-25T10:00:00Z", "carts"), "novel_templates"] == 1
    assert novelty.loc[("2026-10-25T10:01:00Z", "carts"), "novel_templates"] == 1
    assert novelty.loc[("2026-10-25T10:01:00Z", "carts"), "novel_lines"] == 4


def test_a_known_template_in_a_later_bucket_is_not_novel() -> None:
    rows = [
        ("2026-10-25T10:00:01Z", "carts", "order 1 accepted"),
        ("2026-10-25T10:00:40Z", "carts", "order 2 accepted"),
    ]
    novelty = extract_templates(_logs(rows), START).novelty
    assert novelty["novel_templates"].tolist() == [1, 0]
    assert novelty["novel_lines"].tolist() == [1, 0]


def test_reruns_and_row_order_give_identical_features() -> None:
    logs = _sample()
    first = extract_templates(logs, START)
    again = extract_templates(logs, START)
    reversed_ = extract_templates(logs.iloc[::-1], START)
    assert first.digest() == again.digest() == reversed_.digest()


def test_cluster_widening_reaches_earlier_messages() -> None:
    rows = [
        ("2026-10-25T10:00:01Z", "carts", "user alice logged in"),
        ("2026-10-25T10:00:02Z", "carts", "user bob logged in"),
    ]
    features = extract_templates(_logs(rows), START)
    assert features.templates["template"].tolist() == ["user <*> logged in"]
    assert features.counts["count"].tolist() == [2]


def test_no_usable_lines_gives_empty_features() -> None:
    features = extract_templates(
        _logs([("bad", "carts", "x"), (START, "carts", "")]), START
    )
    assert features.templates.empty and features.counts.empty and features.novelty.empty
    assert features.skipped_lines == 2


def test_bucket_width_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        extract_templates(_sample(), START, bucket_seconds=0)


def test_naive_window_start_is_read_as_utc() -> None:
    aware = extract_templates(_sample(), START)
    naive = extract_templates(_sample(), "2026-10-25T10:00:00")
    assert aware.digest() == naive.digest()


def _window(
    tmp_path: Path, phase: EvaluationPhase, logs: bool = True
) -> TelemetryWindow:
    path = None
    if logs:
        (tmp_path / "w").mkdir()
        pq.write_table(
            pa.Table.from_pandas(_sample(), preserve_index=False),
            tmp_path / "w" / "p3.parquet",
        )
        path = "w/p3.parquet"
    return TelemetryWindow(
        incident_id="abc",
        variant_config_hash="h",
        window_start_iso=START,
        window_end_iso="2026-10-25T10:05:00Z",
        evaluation_phase=phase,
        p3_logs_path=path,
    )


def test_features_for_window_resolves_relative_paths(tmp_path: Path) -> None:
    window = _window(tmp_path, EvaluationPhase.EXPLORATORY)
    features = features_for_window(window, tmp_path)
    assert features is not None
    assert features.digest() == extract_templates(_sample(), START).digest()


def test_features_for_window_without_logs(tmp_path: Path) -> None:
    window = _window(tmp_path, EvaluationPhase.EXPLORATORY, logs=False)
    assert features_for_window(window, tmp_path) is None


def test_confirmatory_windows_go_through_the_pool_lock(tmp_path: Path) -> None:
    window = _window(tmp_path, EvaluationPhase.CONFIRMATORY)

    def locked(incident_id: str) -> None:
        raise PoolLockedError(incident_id)

    with pytest.raises(PoolLockedError):
        features_for_window(window, tmp_path, pool_lock=locked)
    assert features_for_window(window, tmp_path, pool_lock=lambda _: None) is not None


def test_micro_second_durations_are_masked_in_both_spellings() -> None:
    rows = [
        (f"2026-10-25T10:00:0{i}Z", "carts", f"took {i + 2}{unit}")
        for i, unit in enumerate((chr(0xB5) + "s", chr(0x3BC) + "s", "ms"))
    ]
    features = extract_templates(_logs(rows), START)
    assert features.templates["template"].tolist() == ["took <DUR>"]
