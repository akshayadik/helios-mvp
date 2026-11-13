"""DuckDB result store — insert and inclusion-rate helper (§3.7).

ResultStore manages the result_row + schema_tag tables defined in schema.sql.
VCLManifest provides variant_config_hash; inclusion_rate() supports C1 gate (§5.1).
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb

from helios.vcl.utils import canonical_json

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from helios.consensus.mahc import FusedVerdict
    from helios.consensus.verdict import ConsensusVerdict
    from helios.schemas.verdict import PipelineName, PipelineVerdict
    from helios.telemetry.trigger import TriggerRecord

__all__ = ["GRAPH_TIMING", "ResultStore"]

# timing_row.pipeline value of the graph build (S4.9 M-a); not a pipeline.
GRAPH_TIMING = "ueg_c"

_PIPELINES = frozenset({"dpipe", "gpipe", "lpipe"})
_SCHEMA_SQL = Path(__file__).parent / "schema.sql"
_ARCHIVE_TABLE = "result_row_v04"


class ResultStore:
    """Thin DuckDB wrapper for pipeline verdict rows.

    Creates the schema on first use. Each instance holds one connection.
    """

    def __init__(self, db_path: Path) -> None:
        self._con = duckdb.connect(str(db_path))
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._migrate_cpr_to_mrr()
        self._archive_pre_v05()
        self._con.execute(_SCHEMA_SQL.read_text(encoding="utf-8"))
        self._add_trigger_known_at()

    def _add_trigger_known_at(self) -> None:
        """Add trigger_row.known_at_s to a database created before S2-BL-12.

        Existing rows keep NULL: their live-detection time was never recorded.
        """
        if "known_at_s" not in self._result_row_columns("trigger_row"):
            self._con.execute("ALTER TABLE trigger_row ADD COLUMN known_at_s DOUBLE")

    def _result_row_columns(self, table: str = "result_row") -> set[str]:
        return {
            r[0]
            for r in self._con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'main' AND table_name = ?",
                [table],
            ).fetchall()
        }

    def _archive_pre_v05(self) -> None:
        """Keep a pre-schema-draft-v0.5 result_row as result_row_v04, untouched.

        Its rows lack the verdict contract (status, mu, sigma, cost), so they
        are not converted; the new result_row is created empty beside them.
        """
        cols = self._result_row_columns()
        if not cols or "status" in cols:
            return
        if self._result_row_columns(_ARCHIVE_TABLE):
            raise RuntimeError(
                f"result_row predates schema-draft-v0.5 and {_ARCHIVE_TABLE} "
                "already exists; refusing to overwrite an archive"
            )
        self._con.execute(f"ALTER TABLE result_row RENAME TO {_ARCHIVE_TABLE}")

    def _migrate_cpr_to_mrr(self) -> None:
        """Rename result_row.cpr to mrr in databases created before schema-draft-v0.4.

        The column always held reciprocal rank; CpR is cost per resolution
        (docs/tracking/metric_contract.md). Values are unchanged.
        """
        cols = self._result_row_columns()
        if "cpr" in cols and "mrr" not in cols:
            self._con.execute("ALTER TABLE result_row RENAME COLUMN cpr TO mrr")

    def table_names(self) -> list[str]:
        rows = self._con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        return [r[0] for r in rows]

    def schema_tags(self) -> list[str]:
        rows = self._con.execute("SELECT tag FROM schema_tag").fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Insert
    # ------------------------------------------------------------------

    def insert(self, verdict: PipelineVerdict) -> None:
        """Insert a PipelineVerdict row. Raises on duplicate run_id (PRIMARY KEY)."""
        self._con.execute(
            """
            INSERT INTO result_row (
                run_id, incident_id, variant_config_hash, snapshot_hash,
                pipeline, evaluation_phase, status, ranked_candidates,
                candidate_scores, mu, sigma, prompt_tokens, completion_tokens,
                cpu_ms, gpu_ms, latency_ms, narrative, prompt_version,
                decision_hash, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                verdict.run_id,
                verdict.incident_id,
                verdict.variant_config_hash,
                verdict.snapshot_hash,
                verdict.pipeline.value,
                verdict.evaluation_phase.value,
                verdict.status.value,
                json.dumps(verdict.ranked_candidates),
                json.dumps(verdict.candidate_scores, sort_keys=True),
                verdict.mu,
                verdict.sigma,
                verdict.cost.prompt_tokens,
                verdict.cost.completion_tokens,
                verdict.cost.cpu_ms,
                verdict.cost.gpu_ms,
                verdict.latency_ms,
                verdict.narrative,
                verdict.prompt_version,
                verdict.compute_decision_hash(),
                verdict.schema_version,
            ],
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def fetch_all(self) -> list[dict[str, object]]:
        """Return all rows as list of dicts."""
        cur = self._con.execute("SELECT * FROM result_row")
        desc = cur.description or []
        cols = [d[0] for d in desc]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    def fetch_all_for_incident(self, incident_id: str) -> list[dict[str, object]]:
        """Return all verdict rows for a specific incident_id."""
        cur = self._con.execute(
            "SELECT * FROM result_row WHERE incident_id = ?", [incident_id]
        )
        rows = cur.fetchall()
        desc = cur.description or []
        cols = [d[0] for d in desc]
        return [dict(zip(cols, row, strict=False)) for row in rows]

    def inclusion_rate(self, variant_config_hash: str) -> float:
        """Fraction of expected pipelines (dpipe/gpipe/lpipe) present for this variant hash.

        Returns a value in [0, 1]. Used by the C1 run-level inclusion gate (§5.1).
        """
        row = self._con.execute(
            """
            SELECT COUNT(DISTINCT pipeline) AS n
            FROM result_row
            WHERE variant_config_hash = ?
              AND pipeline IN ('dpipe', 'gpipe', 'lpipe')
            """,
            [variant_config_hash],
        ).fetchone()
        n = row[0] if row else 0
        return n / len(_PIPELINES)

    def insert_consensus(self, cv: ConsensusVerdict) -> None:
        """Insert a ConsensusVerdict row. Duplicate (incident_id, variant) is silently ignored."""
        self._con.execute(
            """
            INSERT OR IGNORE INTO consensus_verdict
            (incident_id, variant, top_candidates, borda_scores, candidate_universe_size,
             consensus_rank, fusion_algorithm, fusion_algorithm_sha, cpr,
             pipeline_row_count, run_id, timestamp_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                cv.incident_id,
                cv.variant,
                json.dumps(cv.top_candidates),
                json.dumps(cv.borda_scores),
                cv.candidate_universe_size,
                cv.consensus_rank,
                cv.fusion_algorithm,
                cv.fusion_algorithm_sha,
                cv.cpr,
                cv.pipeline_row_count,
                cv.run_id,
                cv.timestamp_utc,
            ],
        )

    def fetch_all_pipeline_rows(self) -> list[dict[str, object]]:
        """Return all rows from result_row as a list of dicts."""
        cur = self._con.execute("SELECT * FROM result_row")
        desc = cur.description or []
        cols = [d[0] for d in desc]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    def fetch_all_consensus_rows(self) -> list[dict[str, object]]:
        """Return all rows from consensus_verdict as a list of dicts."""
        cur = self._con.execute("SELECT * FROM consensus_verdict")
        desc = cur.description or []
        cols = [d[0] for d in desc]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Scores (S1.9) — written by the scoring path only, after dispatch
    # ------------------------------------------------------------------

    def replace_scores(self, rows: list[dict[str, object]]) -> None:
        """Insert score rows, replacing any earlier score of the same list."""
        if not rows:
            return
        cols = list(rows[0])
        placeholders = ", ".join("?" for _ in cols)
        self._con.executemany(
            f"INSERT OR REPLACE INTO eval_score ({', '.join(cols)}) "
            f"VALUES ({placeholders})",
            [[row[c] for c in cols] for row in rows],
        )

    def fetch_scores(self) -> list[dict[str, object]]:
        """Return all rows from eval_score as a list of dicts."""
        cur = self._con.execute(
            "SELECT * FROM eval_score ORDER BY list_kind, source, incident_id, run_id"
        )
        desc = cur.description or []
        cols = [d[0] for d in desc]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Trigger and timings (S2.1) — written by the runner, read by scoring,
    # TTCD/TTT tooling and the baseline harness
    # ------------------------------------------------------------------

    def insert_trigger(
        self,
        record: TriggerRecord,
        *,
        run_id: str,
        variant_config_hash: str,
        seeds_from_trigger: bool,
        handover_unix: float,
    ) -> None:
        """Store the trigger a run handed to every system."""
        self._con.execute(
            """
            INSERT INTO trigger_row (
                run_id, incident_id, variant_config_hash, trigger_time_s,
                suspects, context, source, detector_hash, seeds_from_trigger,
                handover_unix, known_at_s
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                record.incident_id,
                variant_config_hash,
                record.trigger_time_s,
                json.dumps(list(record.suspects)),
                json.dumps(list(record.context)),
                record.source.value,
                record.detector_hash,
                seeds_from_trigger,
                handover_unix,
                record.known_at_s,
            ],
        )

    def insert_evidence(
        self, run_id: str, incident_id: str, pipeline: str, evidence: dict[str, Any]
    ) -> None:
        """Store a pipeline's per-suspect evidence for one run (S2.2)."""
        self._con.execute(
            "INSERT INTO evidence_row (run_id, incident_id, pipeline, evidence_json) "
            "VALUES (?, ?, ?, ?)",
            [run_id, incident_id, pipeline, canonical_json(evidence)],
        )

    def insert_fusion(
        self,
        run_id: str,
        incident_id: str,
        variant_config_hash: str,
        fused: FusedVerdict,
    ) -> None:
        """Store what HELIOS published for one run (S2.5)."""
        sched = fused.schedule
        self._con.execute(
            "INSERT INTO fusion_row (run_id, incident_id, variant_config_hash, method, "
            "ranked_json, scores_json, confidence, fused_sigma, state, first_ms, "
            "first_ranked_json, terminal_ms, non_converged, evidence_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                incident_id,
                variant_config_hash,
                fused.method,
                json.dumps(list(fused.ranked)),
                canonical_json(fused.scores),
                fused.confidence,
                fused.fused_sigma,
                fused.state.value,
                sched.first_ms,
                json.dumps(list(fused.first_ranked)),
                sched.terminal_ms,
                sched.non_converged,
                canonical_json(fused.evidence),
            ],
        )

    def _fusion_rows(self, where: str, args: list[Any]) -> list[dict[str, Any]]:
        cur = self._con.execute(f"SELECT * FROM fusion_row {where}", args)
        cols = [d[0] for d in cur.description or []]
        out = []
        for values in cur.fetchall():
            row = dict(zip(cols, values, strict=True))
            for key in ("ranked", "scores", "first_ranked", "evidence"):
                row[key] = json.loads(row.pop(f"{key}_json"))
            row["non_converged"] = bool(row["non_converged"])
            out.append(row)
        return out

    def fetch_fusion(self, run_id: str) -> dict[str, Any] | None:
        """The fused verdict of one run, or None."""
        rows = self._fusion_rows("WHERE run_id = ?", [run_id])
        return rows[0] if rows else None

    def fetch_all_fusion_rows(self) -> list[dict[str, Any]]:
        """Every fused verdict, ordered by run."""
        return self._fusion_rows("ORDER BY run_id", [])

    def insert_hstruct(
        self,
        run_id: str,
        incident_id: str,
        pipeline: str,
        *,
        outputs: int,
        failed: int,
        structural_zero: bool,
    ) -> None:
        """Agent outputs and schema failures of one run's pipeline (S2.4, H_struct)."""
        self._con.execute(
            "INSERT INTO hstruct_row (run_id, incident_id, pipeline, outputs, failed, "
            "structural_zero) VALUES (?, ?, ?, ?, ?, ?)",
            [run_id, incident_id, pipeline, outputs, failed, structural_zero],
        )

    def insert_narrative(
        self, run_id: str, incident_id: str, step: Mapping[str, Any]
    ) -> None:
        """Store a run's narrative (S2.8): CoE step N plus counts for the report."""
        slots = step["slots"]
        self._con.execute(
            "INSERT INTO narrative_row (run_id, incident_id, narrator, slots_json, "
            "rendered, attempts, fallbacks, prompt_tokens, completion_tokens, "
            "wall_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                incident_id,
                step["narrator"],
                canonical_json(slots),
                step["rendered"],
                sum(int(s["attempts"]) for s in slots.values()),
                sum(bool(s["fallback"]) for s in slots.values()),
                int(step["cost"]["prompt_tokens"]),
                int(step["cost"]["completion_tokens"]),
                float(step["measured"]["wall_ms"]),
            ],
        )

    def _narrative_rows(self, where: str, args: list[Any]) -> list[dict[str, Any]]:
        cur = self._con.execute(f"SELECT * FROM narrative_row {where}", args)
        cols = [d[0] for d in cur.description or []]
        out = []
        for values in cur.fetchall():
            row = dict(zip(cols, values, strict=True))
            row["slots"] = json.loads(row.pop("slots_json"))
            out.append(row)
        return out

    def fetch_narrative(self, run_id: str) -> dict[str, Any] | None:
        """The narrative of one run, or None."""
        rows = self._narrative_rows("WHERE run_id = ?", [run_id])
        return rows[0] if rows else None

    def fetch_all_narrative_rows(self) -> list[dict[str, Any]]:
        """Every stored narrative, ordered by run."""
        return self._narrative_rows("ORDER BY run_id", [])

    def fetch_hstruct(self, run_id: str) -> list[dict[str, Any]]:
        """The H_struct counts of a run, one per pipeline."""
        rows = self._con.execute(
            "SELECT pipeline, outputs, failed, structural_zero FROM hstruct_row "
            "WHERE run_id = ? ORDER BY pipeline",
            [run_id],
        ).fetchall()
        return [
            {"pipeline": p, "outputs": o, "failed": f, "structural_zero": bool(z)}
            for p, o, f, z in rows
        ]

    def fetch_evidence(self, run_id: str, pipeline: str) -> dict[str, Any] | None:
        """The stored evidence of a run's pipeline, or None."""
        row = self._con.execute(
            "SELECT evidence_json FROM evidence_row WHERE run_id = ? AND pipeline = ?",
            [run_id, pipeline],
        ).fetchone()
        return None if row is None else dict(json.loads(row[0]))

    def fetch_trigger(
        self, incident_id: str, variant_config_hash: str
    ) -> TriggerRecord | None:
        """The latest stored trigger of an incident under a variant, or None."""
        from helios.telemetry.trigger import TriggerRecord, TriggerSource

        row = self._con.execute(
            """
            SELECT incident_id, trigger_time_s, suspects, context, source,
                   detector_hash, known_at_s
            FROM trigger_row
            WHERE incident_id = ? AND variant_config_hash = ?
            ORDER BY stored_at DESC, run_id DESC
            LIMIT 1
            """,
            [incident_id, variant_config_hash],
        ).fetchone()
        if row is None:
            return None
        return TriggerRecord(
            incident_id=row[0],
            trigger_time_s=row[1],
            suspects=tuple(json.loads(row[2])),
            context=tuple(json.loads(row[3])),
            source=TriggerSource(row[4]),
            detector_hash=row[5],
            known_at_s=row[6],
        )

    def insert_timing(
        self,
        run_id: str,
        pipeline: PipelineName,
        started_unix: float,
        published_unix: float,
    ) -> None:
        """Wall-clock start and publication of one pipeline's verdict."""
        self._con.execute(
            "INSERT INTO timing_row (run_id, pipeline, started_unix, published_unix) "
            "VALUES (?, ?, ?, ?)",
            [run_id, pipeline.value, started_unix, published_unix],
        )

    def fetch_timings(self, run_id: str) -> list[dict[str, object]]:
        """Timing rows of a run, in order of publication."""
        cur = self._con.execute(
            "SELECT * FROM timing_row WHERE run_id = ? "
            "ORDER BY published_unix, pipeline",
            [run_id],
        )
        cols = [d[0] for d in cur.description or []]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    def insert_graph_timing(
        self, run_id: str, started_unix: float, published_unix: float
    ) -> None:
        """Wall-clock graph build of a run (S4.9 M-a): timing row ``ueg_c``."""
        self._con.execute(
            "INSERT INTO timing_row (run_id, pipeline, started_unix, published_unix) "
            "VALUES (?, ?, ?, ?)",
            [run_id, GRAPH_TIMING, started_unix, published_unix],
        )

    def fetch_trigger_row(self, run_id: str) -> dict[str, Any] | None:
        """The trigger row of one run (handover, source, times), or None."""
        cur = self._con.execute(
            "SELECT run_id, incident_id, trigger_time_s, source, handover_unix, "
            "known_at_s FROM trigger_row WHERE run_id = ?",
            [run_id],
        )
        cols = [d[0] for d in cur.description or []]
        row = cur.fetchone()
        return None if row is None else dict(zip(cols, row, strict=True))

    def fetch_run_pipeline_rows(self, run_id: str) -> list[dict[str, object]]:
        """The pipeline result rows of one run, ordered by pipeline."""
        cur = self._con.execute(
            "SELECT * FROM result_row WHERE run_id = ? ORDER BY pipeline", [run_id]
        )
        cols = [d[0] for d in cur.description or []]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Routing record and run-level metrics (S4.9)
    # ------------------------------------------------------------------

    def insert_routing(
        self, run_id: str, incident_id: str, routing: Mapping[str, Any]
    ) -> None:
        """Store a run's routing record (the CoE R step's content)."""
        self._con.execute(
            "INSERT INTO routing_row (run_id, incident_id, routing_json) "
            "VALUES (?, ?, ?)",
            [run_id, incident_id, canonical_json(dict(routing))],
        )

    def fetch_routing(self, run_id: str) -> dict[str, Any] | None:
        """The routing record of one run, or None (runs stored before S4.9)."""
        row = self._con.execute(
            "SELECT routing_json FROM routing_row WHERE run_id = ?", [run_id]
        ).fetchone()
        return None if row is None else dict(json.loads(row[0]))

    def replace_run_metrics(self, rows: list[dict[str, object]]) -> None:
        """Insert eval_run rows, replacing any earlier row of the same run."""
        if not rows:
            return
        cols = list(rows[0])
        placeholders = ", ".join("?" for _ in cols)
        self._con.executemany(
            f"INSERT OR REPLACE INTO eval_run ({', '.join(cols)}) "
            f"VALUES ({placeholders})",
            [[row[c] for c in cols] for row in rows],
        )

    def fetch_run_metrics(self) -> list[dict[str, object]]:
        """Every eval_run row, ordered by run."""
        cur = self._con.execute("SELECT * FROM eval_run ORDER BY run_id")
        cols = [d[0] for d in cur.description or []]
        return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Baselines (S4.8)
    # ------------------------------------------------------------------

    _BASELINE_JSON = ("ranked", "raw_ranks")

    def insert_baseline(self, row: Mapping[str, Any]) -> None:
        """Store one baseline run (``ranked`` and ``raw_ranks`` as lists)."""
        values = dict(row)
        for key in self._BASELINE_JSON:
            values[f"{key}_json"] = json.dumps(list(values.pop(key)))
        cols = list(values)
        self._con.execute(
            f"INSERT INTO baseline_row ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [values[c] for c in cols],
        )

    def fetch_baseline(self, run_id: str) -> dict[str, Any] | None:
        """One baseline run, or None."""
        rows = self._baseline_rows("WHERE run_id = ?", [run_id])
        return rows[0] if rows else None

    def fetch_all_baseline_rows(self) -> list[dict[str, Any]]:
        """Every baseline run, ordered by source and incident."""
        return self._baseline_rows("ORDER BY source, incident_id, run_id", [])

    def _baseline_rows(self, where: str, args: list[Any]) -> list[dict[str, Any]]:
        cur = self._con.execute(f"SELECT * FROM baseline_row {where}", args)
        cols = [d[0] for d in cur.description or []]
        out = []
        for values in cur.fetchall():
            row = dict(zip(cols, values, strict=True))
            for key in self._BASELINE_JSON:
                row[key] = json.loads(row.pop(f"{key}_json"))
            out.append(row)
        return out

    # ------------------------------------------------------------------
    # Run atomicity (S4.10 O-c, O-i)
    # ------------------------------------------------------------------

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        """Every write of one run commits together or not at all."""
        self._con.execute("BEGIN TRANSACTION")
        try:
            yield
        except BaseException:
            self._con.execute("ROLLBACK")
            raise
        self._con.execute("COMMIT")

    def delete_run(self, run_id: str) -> int:
        """Remove every row of ``run_id`` (an unfinished run before its retry)."""
        removed = 0
        for (table,) in self._con.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'main' AND column_name = 'run_id' "
            "ORDER BY table_name"
        ).fetchall():
            before = self._count(table, run_id)
            self._con.execute(f'DELETE FROM "{table}" WHERE run_id = ?', [run_id])
            removed += before
        return removed

    def _count(self, table: str, run_id: str) -> int:
        row = self._con.execute(
            f'SELECT count(*) FROM "{table}" WHERE run_id = ?', [run_id]
        ).fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._con.close()
