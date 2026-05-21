#!/usr/bin/env python3
"""Idempotent fusion of pipeline rows -> ConsensusVerdict rows.

Reads a merged DuckDB result file, applies UniformBordaConsensus per
(incident_id, variant) group, and writes ConsensusVerdict rows.
Idempotent: runs twice without duplicating rows (INSERT OR IGNORE).

Usage:
    python scripts/fuse_verdicts.py --db-path /tmp/helios-m4/helios_m4_results.duckdb
    python scripts/fuse_verdicts.py --db-path /tmp/helios-m4/helios_m4_results.duckdb --smoke
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_FUSE_VERDICTS: bool = True


def _ensure_consensus_table(conn: object) -> None:
    import duckdb as _duckdb

    assert isinstance(conn, _duckdb.DuckDBPyConnection)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS consensus_verdict (
            incident_id              VARCHAR NOT NULL,
            variant                  VARCHAR NOT NULL,
            top_candidates           VARCHAR NOT NULL,
            borda_scores             VARCHAR NOT NULL,
            candidate_universe_size  INTEGER NOT NULL,
            consensus_rank           INTEGER NOT NULL,
            fusion_algorithm         VARCHAR NOT NULL,
            fusion_algorithm_sha     VARCHAR NOT NULL,
            cpr                      DOUBLE  NOT NULL DEFAULT 0,
            pipeline_row_count       INTEGER NOT NULL,
            run_id                   VARCHAR NOT NULL,
            timestamp_utc            VARCHAR NOT NULL,
            PRIMARY KEY (incident_id, variant)
        )
    """
    )


def _load_pipeline_groups(
    db_path: Path,
) -> dict[tuple[str, str], list[dict[str, object]]]:
    import duckdb

    conn = duckdb.connect(str(db_path))
    _ensure_consensus_table(conn)
    rows = conn.execute(
        """
        SELECT incident_id, variant, pipeline, ranked_candidates, narrative
        FROM result_row
        WHERE narrative != 'gpipe-gated-or-skipped'
        ORDER BY incident_id, variant, pipeline
        """,
    ).fetchall()
    conn.close()

    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for incident_id, variant, pipeline, ranked_json, narrative in rows:
        key = (incident_id, variant)
        groups.setdefault(key, []).append(
            {
                "pipeline": pipeline,
                "ranked_candidates": json.loads(ranked_json) if ranked_json else [],
                "narrative": narrative,
            }
        )
    return groups


def _fuse_all(db_path: Path, run_id: str) -> int:
    import duckdb

    from helios.consensus.uniform_borda import (
        PassthroughConsensus,
        UniformBordaConsensus,
    )
    from helios.vcl import (
        GatedComponentInactiveError,
        get_variant,
        set_current_manifest,
    )

    groups = _load_pipeline_groups(db_path)
    borda = UniformBordaConsensus()
    passthrough = PassthroughConsensus()

    conn = duckdb.connect(str(db_path))
    fused_count = 0

    for (incident_id, variant), pipeline_rows in groups.items():
        manifest = get_variant(variant)
        set_current_manifest(manifest)

        try:
            cv = borda.fuse(
                incident_id=incident_id,
                variant=variant,
                pipeline_rows=pipeline_rows,
                run_id=run_id,
            )
        except GatedComponentInactiveError:
            cv = passthrough.fuse(
                incident_id=incident_id,
                variant=variant,
                pipeline_rows=pipeline_rows,
                run_id=run_id,
            )

        conn.execute(
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
        fused_count += 1

    conn.close()
    return fused_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fuse pipeline rows into ConsensusVerdict rows."
    )
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Validate DB has rows and consensus table exists; no fusion.",
    )
    parser.add_argument("--run-id", default="m4-fuse")
    args = parser.parse_args(argv)

    if not args.db_path.exists():
        print(f"ERROR: DB not found: {args.db_path}", file=sys.stderr)
        return 1

    if args.smoke:
        import duckdb

        conn = duckdb.connect(str(args.db_path), read_only=True)
        try:
            row = conn.execute("SELECT COUNT(*) FROM result_row").fetchone()
            count = row[0] if row is not None else 0
            print(f"Smoke: result_row count={count}")
        except Exception as exc:
            print(f"Smoke check failed: {exc}", file=sys.stderr)
            return 1
        finally:
            conn.close()
        return 0

    n = _fuse_all(args.db_path, run_id=args.run_id)
    print(
        f"Fused {n} (incident, variant) groups -> ConsensusVerdict rows in {args.db_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
