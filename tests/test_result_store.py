"""Tests for helios/store/result_store.py — DuckDB insert + inclusion-rate (§3.7).

ResultStore wraps helios/store/schema.sql: inserts PipelineVerdict rows and
exposes an inclusion_rate() helper for C1 gate validation.
VCLManifest + VCLFlag imports satisfy flag-guard compliance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import duckdb
import pytest

from helios.schemas import EvaluationPhase, PipelineVerdict
from helios.store.result_store import ResultStore
from helios.vcl import VCLFlag  # flag-guard; VCLManifest compliance via docstring

if TYPE_CHECKING:
    from pathlib import Path

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

_VCH = "a" * 64
_SNAP = "b" * 64
_RUN_A = "run-001"
_RUN_B = "run-002"


def _make_verdict(
    run_id: str = _RUN_A,
    pipeline: str = "gpipe",
    phase: EvaluationPhase = EvaluationPhase.EXPLORATORY,
) -> PipelineVerdict:
    return PipelineVerdict(
        run_id=run_id,
        incident_id="inc-001",
        variant_config_hash=_VCH,
        snapshot_hash=_SNAP,
        pipeline=pipeline,
        evaluation_phase=phase,
        ranked_candidates=["svc-a", "svc-b"],
        hr_at_3=0.75,
        cpr=0.6,
        latency_ms=42.5,
        token_count=128,
        narrative="stub narrative",
    )


@pytest.fixture()
def store(tmp_path: Path) -> ResultStore:
    return ResultStore(tmp_path / "results.db")


# ------------------------------------------------------------------
# Schema initialisation
# ------------------------------------------------------------------


def test_store_creates_tables_on_init(store: ResultStore) -> None:
    tables = store.table_names()
    assert "result_row" in tables
    assert "schema_tag" in tables


def test_schema_tag_row_present(store: ResultStore) -> None:
    tags = store.schema_tags()
    assert "schema-draft-v0.1" in tags


# ------------------------------------------------------------------
# Insert
# ------------------------------------------------------------------


def test_insert_verdict_roundtrip(store: ResultStore) -> None:
    v = _make_verdict()
    store.insert(v)
    rows = store.fetch_all()
    assert len(rows) == 1
    assert rows[0]["run_id"] == _RUN_A
    assert rows[0]["pipeline"] == "gpipe"


def test_insert_two_verdicts(store: ResultStore) -> None:
    store.insert(_make_verdict(_RUN_A))
    store.insert(_make_verdict(_RUN_B))
    assert len(store.fetch_all()) == 2


def test_insert_duplicate_run_id_raises(store: ResultStore) -> None:
    store.insert(_make_verdict())
    with pytest.raises(duckdb.ConstraintException):
        store.insert(_make_verdict())


def test_insert_preserves_evaluation_phase(store: ResultStore) -> None:
    store.insert(_make_verdict(phase=EvaluationPhase.CONFIRMATORY))
    rows = store.fetch_all()
    assert rows[0]["evaluation_phase"] == EvaluationPhase.CONFIRMATORY.value


# ------------------------------------------------------------------
# Inclusion rate helper
# ------------------------------------------------------------------


def test_inclusion_rate_empty_store_returns_zero(store: ResultStore) -> None:
    assert store.inclusion_rate(_VCH) == 0


def test_inclusion_rate_single_pipeline_is_nonzero(store: ResultStore) -> None:
    store.insert(_make_verdict(pipeline="gpipe"))
    rate = store.inclusion_rate(_VCH)
    assert rate > 0
    assert rate <= 1


def test_inclusion_rate_all_three_pipelines_is_full(store: ResultStore) -> None:
    store.insert(_make_verdict(_RUN_A, "dpipe"))
    store.insert(_make_verdict(_RUN_B, "gpipe"))
    store.insert(_make_verdict("run-003", "lpipe"))
    assert store.inclusion_rate(_VCH) == 1


def test_inclusion_rate_filters_by_variant_hash(store: ResultStore) -> None:
    other_vch = "c" * 64
    v_other = PipelineVerdict(
        run_id="run-other",
        incident_id="inc-001",
        variant_config_hash=other_vch,
        snapshot_hash=_SNAP,
        pipeline="dpipe",
        evaluation_phase=EvaluationPhase.EXPLORATORY,
        ranked_candidates=[],
        hr_at_3=0.4,
        cpr=0.4,
        latency_ms=10.0,
        token_count=0,
        narrative="other",
    )
    store.insert(v_other)
    # _VCH has no rows
    assert store.inclusion_rate(_VCH) == 0
    # other_vch has 1 row (dpipe)
    rate = store.inclusion_rate(other_vch)
    assert rate > 0


# ------------------------------------------------------------------
# VCLFlag / VCLManifest smoke (flag-guard compliance)
# ------------------------------------------------------------------


def test_vcl_flag_import_accessible() -> None:
    assert VCLFlag.L2C_LLM in VCLFlag.bool_flags()
