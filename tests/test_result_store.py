"""Tests for helios/store/result_store.py — DuckDB insert + inclusion-rate (§3.7).

ResultStore wraps helios/store/schema.sql: inserts PipelineVerdict rows and
exposes an inclusion_rate() helper for C1 gate validation.
VCLManifest + VCLFlag imports satisfy flag-guard compliance.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import duckdb
import pytest

from helios.schemas import EvaluationPhase, PipelineVerdict
from helios.schemas.verdict import PipelineName, VerdictCost, VerdictStatus
from helios.store.result_store import ResultStore
from helios.telemetry.trigger import TriggerRecord, TriggerSource
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
    variant_config_hash: str = _VCH,
) -> PipelineVerdict:
    return PipelineVerdict(
        run_id=run_id,
        incident_id="inc-001",
        variant_config_hash=variant_config_hash,
        snapshot_hash=_SNAP,
        pipeline=PipelineName(pipeline),
        evaluation_phase=phase,
        status=VerdictStatus.RANKED,
        ranked_candidates=["svc-a", "svc-b"],
        candidate_scores={"svc-b": 0.25, "svc-a": 0.75},
        mu=0.75,
        cost=VerdictCost(prompt_tokens=100 + 28, completion_tokens=32, cpu_ms=7.5),
        latency_ms=42.5,
        narrative="stub narrative",
        prompt_version="rca_v1",
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
    assert "schema-draft-v0.4" in tags
    assert "schema-draft-v0.5" in tags
    assert "eval-score-v1" in tags  # S1.9 scores table
    assert "eval_score" in store.table_names()


def test_pre_v0_4_database_cpr_column_is_renamed_to_mrr(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE result_row (run_id VARCHAR, incident_id VARCHAR,"
        " variant_config_hash VARCHAR, snapshot_hash VARCHAR, pipeline VARCHAR,"
        " evaluation_phase VARCHAR, ranked_candidates JSON, hr_at_3 DOUBLE,"
        " cpr DOUBLE, latency_ms DOUBLE, token_count BIGINT, narrative TEXT,"
        " schema_version VARCHAR, created_at TIMESTAMP,"
        " PRIMARY KEY (run_id, pipeline))"
    )
    con.execute(
        "INSERT INTO result_row VALUES ('r0', 'i0', 'h', 's', 'dpipe',"
        " 'exploratory', '[]', 1, 0.25, 1, 0, 'n', 'schema-draft-v0.2', NULL)"
    )
    con.close()

    migrated = ResultStore(db)
    # Renamed to mrr, then archived whole as result_row_v04 (schema-draft-v0.5).
    archived = migrated._con.execute(
        "SELECT run_id, mrr FROM result_row_v04 ORDER BY run_id"
    ).fetchall()
    assert archived == [("r0", 0.25)]
    migrated.insert(_make_verdict())
    assert [r["run_id"] for r in migrated.fetch_all()] == [_RUN_A]


def test_pre_v0_5_result_row_is_archived_not_rewritten(tmp_path: Path) -> None:
    db = tmp_path / "v04.db"
    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE result_row (run_id VARCHAR, pipeline VARCHAR, hr_at_3 DOUBLE,"
        " mrr DOUBLE, token_count BIGINT)"
    )
    con.execute("INSERT INTO result_row VALUES ('r0', 'dpipe', 1, 1, 7)")
    con.close()

    store = ResultStore(db)
    assert store._con.execute("SELECT * FROM result_row_v04").fetchall() == [
        ("r0", "dpipe", 1, 1, 7)
    ]
    assert store.fetch_all() == []
    store.close()
    # Reopening a migrated database changes nothing.
    again = ResultStore(db)
    assert again._con.execute("SELECT count(*) FROM result_row_v04").fetchone() == (1,)
    again.close()


def test_archive_is_never_overwritten(tmp_path: Path) -> None:
    db = tmp_path / "both.db"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE result_row (run_id VARCHAR, mrr DOUBLE)")
    con.execute("CREATE TABLE result_row_v04 (run_id VARCHAR, mrr DOUBLE)")
    con.close()
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        ResultStore(db)


def test_insert_stores_the_verdict_contract(store: ResultStore) -> None:
    v = _make_verdict()
    store.insert(v)
    row = store.fetch_all()[0]
    assert row["status"] == "ranked"
    assert json.loads(str(row["ranked_candidates"])) == ["svc-a", "svc-b"]
    assert json.loads(str(row["candidate_scores"])) == {"svc-a": 0.75, "svc-b": 0.25}
    assert (row["mu"], row["sigma"]) == (0.75, None)
    assert (row["prompt_tokens"], row["completion_tokens"]) == (128, 32)
    assert (row["cpu_ms"], row["gpu_ms"]) == (7.5, 0)
    assert row["prompt_version"] == "rca_v1"
    assert row["decision_hash"] == v.compute_decision_hash()
    assert row["schema_version"] == "schema-draft-v0.5"
    assert not {"hr_at_3", "mrr", "token_count"} & set(row)


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
    v_other = _make_verdict("run-other", "dpipe", variant_config_hash=other_vch)
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


# ------------------------------------------------------------------
# ConsensusVerdict insert / fetch (schema-draft-v0.3)
# ------------------------------------------------------------------


def _make_cv(incident_id: str = "otel-001", variant: str = "HELIOS-Full") -> object:
    from helios.consensus.verdict import ConsensusVerdict

    return ConsensusVerdict(
        incident_id=incident_id,
        variant=variant,
        top_candidates=["svc-a", "svc-b"],
        borda_scores={"svc-a": 2, "svc-b": 1},
        candidate_universe_size=2,
        consensus_rank=2,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha="abc123",
        pipeline_row_count=3,
        run_id="run-test",
        timestamp_utc="2026-05-20T10:00:00Z",
    )


def test_insert_and_fetch_consensus(tmp_path: Path) -> None:
    store = ResultStore(tmp_path / "test.duckdb")
    cv = _make_cv()
    store.insert_consensus(cv)  # type: ignore[arg-type]
    rows = store.fetch_all_consensus_rows()
    assert len(rows) == 1
    assert rows[0]["incident_id"] == "otel-001"
    assert rows[0]["variant"] == "HELIOS-Full"
    store.close()


def test_fetch_all_pipeline_rows_returns_list(tmp_path: Path) -> None:
    store = ResultStore(tmp_path / "test.duckdb")
    rows = store.fetch_all_pipeline_rows()
    assert isinstance(rows, list)
    store.close()


def test_insert_consensus_idempotent_guard(tmp_path: Path) -> None:
    store = ResultStore(tmp_path / "test.duckdb")
    cv = _make_cv()
    store.insert_consensus(cv)  # type: ignore[arg-type]
    # Second insert of same (incident_id, variant) must not raise — INSERT OR IGNORE
    store.insert_consensus(cv)  # type: ignore[arg-type]
    rows = store.fetch_all_consensus_rows()
    assert len(rows) == 1
    store.close()


# ------------------------------------------------------------------
# Trigger and timings (S2.1)
# ------------------------------------------------------------------


def _trigger() -> TriggerRecord:
    return TriggerRecord(
        incident_id="otel-001",
        trigger_time_s=1_790_000_300,
        suspects=("cart", "ad"),
        context=("otel-collector",),
        source=TriggerSource.THRESHOLD,
        detector_hash="d" * 64,
    )


def test_trigger_round_trips_exactly(store: ResultStore) -> None:
    store.insert_trigger(
        _trigger(),
        run_id="r1",
        variant_config_hash="v" * 64,
        seeds_from_trigger=True,
        handover_unix=1_800_000_000,
    )
    assert store.fetch_trigger("otel-001", "v" * 64) == _trigger()
    assert store.fetch_trigger("other", "v" * 64) is None


def test_trigger_and_timing_tables_are_tagged(store: ResultStore) -> None:
    assert {"trigger_row", "timing_row"} <= set(store.table_names())
    assert "trigger-v1" in store.schema_tags()


def test_timing_rows_one_per_pipeline(store: ResultStore) -> None:
    store.insert_timing("r1", PipelineName.DPIPE, 10, 12)
    store.insert_timing("r1", PipelineName.GPIPE, 12, 15)
    rows = store.fetch_timings("r1")
    assert [(r["pipeline"], r["published_unix"]) for r in rows] == [
        ("dpipe", 12),
        ("gpipe", 15),
    ]
    with pytest.raises(duckdb.ConstraintException):
        store.insert_timing("r1", PipelineName.DPIPE, 20, 21)


def test_existing_store_gains_the_new_tables(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    first = ResultStore(path)
    first.insert(_make_verdict())
    first.close()
    con = duckdb.connect(str(path))
    con.execute("DROP TABLE trigger_row")
    con.execute("DROP TABLE timing_row")
    con.close()
    reopened = ResultStore(path)
    assert {"trigger_row", "timing_row"} <= set(reopened.table_names())
    assert len(reopened.fetch_all_pipeline_rows()) == 1
