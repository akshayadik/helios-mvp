#!/usr/bin/env python3
"""Inspect ppr_scores column in DuckDB result_row for dpipe rows.

Usage:
    poetry run python scripts/inspect_ppr_scores.py
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_INSPECT_PPR: bool = True

DB_PATH = Path("data/results.duckdb")


def main() -> None:
    con = duckdb.connect(str(DB_PATH))
    rows = con.execute(
        "SELECT incident_id, pipeline, ppr_scores, ranked_candidates "
        "FROM result_row WHERE pipeline='dpipe' LIMIT 5"
    ).fetchall()
    print(f"dpipe rows found: {len(rows)}")
    for r in rows:
        incident_id, pipeline, ppr_scores_raw, ranked_raw = r
        print(f"  {incident_id}  pipeline={pipeline}")
        print(
            f"    ppr_scores type={type(ppr_scores_raw).__name__}  value={repr(ppr_scores_raw)[:120]}"
        )
        print(
            f"    ranked_candidates type={type(ranked_raw).__name__}  value={repr(ranked_raw)[:80]}"
        )
    # Also check the schema
    schema = con.execute("DESCRIBE result_row").fetchall()
    print("\nresult_row schema:")
    for col in schema:
        print(f"  {col[0]:30s}  {col[1]}")


if __name__ == "__main__":
    main()
