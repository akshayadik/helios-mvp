"""DuckDB result store — insert and inclusion-rate helper (§3.7).

ResultStore manages the result_row + schema_tag tables defined in schema.sql.
VCLManifest provides variant_config_hash; inclusion_rate() supports C1 gate (§5.1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from helios.consensus.verdict import ConsensusVerdict
    from helios.schemas.verdict import PipelineVerdict

__all__ = ["ResultStore"]

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
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._con.close()
