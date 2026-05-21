#!/usr/bin/env python3
"""Run the full HELIOS ablation matrix.

Spawns one subprocess per variant (run_one_variant.py), then atomically
merges all per-variant DuckDB files into a central DB.

Usage:
    python scripts/run_ablation.py --output-dir /tmp/helios-m4
    python scripts/run_ablation.py --dry-run --output-dir /tmp/helios-m4
"""

from __future__ import annotations

import argparse
import contextlib
import subprocess
import sys
from pathlib import Path

from helios.config.m4_ablation import EXPECTED_PIPELINE_ROW_COUNT, NUM_VARIANTS
from helios.vcl import get_all_variants
from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_RUN_ABLATION: bool = True


def _dry_run(output_dir: Path) -> int:
    variants = list(get_all_variants().keys())
    print("DRY RUN — no subprocesses spawned")
    print(f"Variants ({NUM_VARIANTS}):")
    for v in variants:
        print(f"  {v}")
    print(f"Expected total pipeline rows: {EXPECTED_PIPELINE_ROW_COUNT}")
    print(f"Output directory (would be created): {output_dir}")
    return 0


_DEFAULT_VARIANT_TIMEOUT_SECONDS: int = 7200  # 2 h; L-pipe x 3 samples x 20 incidents


def _run_variant_subprocess(
    variant_name: str,
    db_path: Path,
    captures_dir: Path,
    registry_path: Path,
    reconciliation_path: Path,
    exclusion_ledger: Path,
    *,
    timeout: int,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/run_one_variant.py",
            "--variant",
            variant_name,
            "--db-path",
            str(db_path),
            "--captures-dir",
            str(captures_dir),
            "--registry-path",
            str(registry_path),
            "--reconciliation-path",
            str(reconciliation_path),
            "--exclusion-ledger",
            str(exclusion_ledger),
        ],
        capture_output=False,
        timeout=timeout,
    )


def _atomic_merge(per_variant_dbs: list[Path], central_db: Path) -> None:
    """Merge all per-variant DBs into central_db atomically.

    Uses a single DuckDB transaction wrapping all inserts:
    - All sources are ATTACHed before the transaction begins.
    - All INSERT OR IGNORE statements run inside one BEGIN/COMMIT block.
    - On any exception, DuckDB rolls back automatically.
    - DETACH runs in a finally block regardless of outcome.
    """
    import duckdb

    aliases: list[str] = []
    conn = duckdb.connect(str(central_db))
    try:
        for idx, db_path in enumerate(per_variant_dbs):
            alias = f"src_{idx}"
            conn.execute(f"ATTACH '{db_path!s}' AS {alias} (READ_ONLY)")
            aliases.append(alias)

        conn.begin()
        try:
            for alias in aliases:
                conn.execute(
                    f"INSERT OR IGNORE INTO result_row SELECT * FROM {alias}.result_row"
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        for alias in aliases:
            with contextlib.suppress(Exception):
                conn.execute(f"DETACH {alias}")
        conn.close()


def _smoke_check(central_db: Path, expected_variants: list[str]) -> bool:
    import duckdb

    conn = duckdb.connect(str(central_db), read_only=True)
    row = conn.execute("SELECT COUNT(*) FROM result_row").fetchone()
    total: int = int(row[0]) if row is not None else 0
    found = {
        r[0] for r in conn.execute("SELECT DISTINCT variant FROM result_row").fetchall()
    }
    conn.close()
    missing = set(expected_variants) - found
    if missing:
        print(f"Smoke check FAIL: missing variants: {missing}", file=sys.stderr)
        return False
    print(
        f"Smoke check OK: {total} pipeline rows, "
        f"{len(found)}/{len(expected_variants)} variants present in {central_db}"
    )
    return total > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run HELIOS ablation matrix.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
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
        "--exclusion-ledger",
        type=Path,
        default=Path("exclusion_ledger.jsonl"),
    )
    parser.add_argument(
        "--variant-timeout",
        type=int,
        default=_DEFAULT_VARIANT_TIMEOUT_SECONDS,
        help=f"Per-variant subprocess timeout in seconds (default: {_DEFAULT_VARIANT_TIMEOUT_SECONDS})",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        return _dry_run(args.output_dir)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    variants = get_all_variants()
    per_variant_dbs: list[Path] = []
    failed: list[str] = []

    for name in variants:
        db_path = args.output_dir / f"{name}.duckdb"
        print(f"Running variant: {name}")
        try:
            proc = _run_variant_subprocess(
                variant_name=name,
                db_path=db_path,
                captures_dir=args.captures_dir,
                registry_path=args.registry_path,
                reconciliation_path=args.reconciliation_path,
                exclusion_ledger=args.exclusion_ledger,
                timeout=args.variant_timeout,
            )
        except subprocess.TimeoutExpired:
            failed.append(name)
            print(
                f"  TIMEOUT: {name} exceeded {args.variant_timeout}s",
                file=sys.stderr,
            )
            continue
        if proc.returncode != 0:
            failed.append(name)
            print(f"  FAILED: {name} exited {proc.returncode}", file=sys.stderr)
        else:
            per_variant_dbs.append(db_path)

    if failed:
        print(f"Variants failed: {failed}", file=sys.stderr)
        return 1

    central_db = args.output_dir / "helios_m4_results.duckdb"
    try:
        _atomic_merge(per_variant_dbs, central_db)
    except Exception as exc:
        print(f"Merge failed: {exc}", file=sys.stderr)
        return 1

    if not _smoke_check(central_db, list(variants.keys())):
        print("Smoke check failed: see details above", file=sys.stderr)
        return 1

    print(f"Ablation run complete. Results at {central_db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
