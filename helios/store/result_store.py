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
        self._con.execute(_SCHEMA_SQL.read_text(encoding="utf-8"))

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
                pipeline, evaluation_phase, ranked_candidates,
                hr_at_3, cpr, latency_ms, token_count, narrative, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                verdict.run_id,
                verdict.incident_id,
                verdict.variant_config_hash,
                verdict.snapshot_hash,
                verdict.pipeline,
                verdict.evaluation_phase.value,
                json.dumps(verdict.ranked_candidates),
                verdict.hr_at_3,
                verdict.cpr,
                verdict.latency_ms,
                verdict.token_count,
                verdict.narrative,
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
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._con.close()
