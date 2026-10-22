#!/usr/bin/env python3
"""10-percent replication check for Milestone 4 ablation results.

Reruns max(1, NUM_INCIDENTS // 10) incidents through all variants and
verifies byte-equality of result_row entries against the target DB.

Usage:
    python scripts/replicate.py --db-path /tmp/helios-m4/helios_m4_results.duckdb \\
        --captures-dir data/captures --output data/replication_log.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from helios.config.m4_ablation import NUM_INCIDENTS
from helios.vcl import get_all_variants
from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_REPLICATE: bool = True

_N_REPLICATE: int = max(1, NUM_INCIDENTS // 10)


def _select_replication_incidents(db_path: Path) -> list[str]:
    import duckdb

    conn = duckdb.connect(str(db_path), read_only=True)
    rows = conn.execute(
        "SELECT DISTINCT incident_id FROM result_row ORDER BY incident_id LIMIT ?",
        [_N_REPLICATE],
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replication check for M4 ablation results."
    )
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--captures-dir", type=Path, default=Path("data/captures"))
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=Path("data/snapshot_registry.jsonl"),
    )
    parser.add_argument(
        "--reconciliation-path",
        type=Path,
        default=Path("data/reconciliation_ledger.jsonl"),
    )
    parser.add_argument(
        "--exclusion-ledger", type=Path, default=Path("exclusion_ledger.jsonl")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/replication_log.json")
    )
    args = parser.parse_args(argv)

    if not args.db_path.exists():
        print(f"ERROR: DB not found: {args.db_path}", file=sys.stderr)
        return 1

    incidents = _select_replication_incidents(args.db_path)
    if not incidents:
        print("ERROR: No incidents in DB to replicate", file=sys.stderr)
        return 1

    print(f"Replicating {len(incidents)} incidents: {incidents}")

    mismatches: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        for variant_name in get_all_variants():
            rep_db = tmp_path / f"{variant_name}_rep.duckdb"
            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/run_one_variant.py",
                    "--variant",
                    variant_name,
                    "--db-path",
                    str(rep_db),
                    "--captures-dir",
                    str(args.captures_dir),
                    "--registry-path",
                    str(args.registry_path),
                    "--reconciliation-path",
                    str(args.reconciliation_path),
                    "--exclusion-ledger",
                    str(args.exclusion_ledger),
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                mismatches.append({"variant": variant_name, "error": proc.stderr})
                continue

            import duckdb

            orig_conn = duckdb.connect(str(args.db_path), read_only=True)
            rep_conn = duckdb.connect(str(rep_db), read_only=True)

            for inc_id in incidents:
                orig_rows = orig_conn.execute(
                    "SELECT * FROM result_row "
                    "WHERE incident_id=? AND variant=? ORDER BY pipeline",
                    [inc_id, variant_name],
                ).fetchall()
                rep_rows = rep_conn.execute(
                    "SELECT * FROM result_row "
                    "WHERE incident_id=? AND variant=? ORDER BY pipeline",
                    [inc_id, variant_name],
                ).fetchall()
                if orig_rows != rep_rows:
                    mismatches.append(
                        {
                            "variant": variant_name,
                            "incident_id": inc_id,
                            "mismatch": True,
                        }
                    )

            orig_conn.close()
            rep_conn.close()

    log: dict[str, object] = {
        "n_replicated": len(incidents),
        "incidents_replicated": incidents,
        "n_variants": len(get_all_variants()),
        "mismatches": mismatches,
        "passed": len(mismatches) == 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(log, indent=2), encoding="utf-8")
    if mismatches:
        print(
            f"REPLICATION FAILED: {len(mismatches)} mismatches. See {args.output}",
            file=sys.stderr,
        )
        return 1
    print(f"Replication passed. Log at {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
