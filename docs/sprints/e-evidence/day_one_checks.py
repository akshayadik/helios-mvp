"""Phase E day-one pool-only checks (S2-M11-EVAL05). Counts only.

Run from the root of a build-freeze-2 worktree with .env loaded:
    poetry run python docs/sprints/e-evidence/day_one_checks.py <out_dir>

Reads each pool window through CaptureReader (pool gate + window hash + seal),
never a label file, and prints aggregate counts only: no case IDs.

Check A: span status-code format. Distinct status_code values in all pool
traces; the three span-error call sites (G-pipe span_features._is_error,
L-pipe digests' error_mask, the export's is_error_span) applied to every
distinct value, and how many windows HELIOS and the export each see errors in.

Check B: the export on every pool window: all six files written, derived
series (logts, tracets_err, tracets_lat) carry columns where the modality
exists, and how many windows have a non-zero error series.

This is the version run from build-freeze-2 (entry 105). The first run, from
build-freeze, compared the old rules (span_features.ERROR_CODES and the v2
export) and found the defect fixed under entry 104; see day_one_checks.md.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

import helios  # noqa: E402
from bin.log_deviation import load_key  # noqa: E402
from helios.baselines.export import (  # noqa: E402
    EXPORT_VERSION,
    export_window,
    is_error_span,
)
from helios.graph.span_features import _is_error  # noqa: E402
from helios.telemetry.reader import CaptureReader  # noqa: E402
from helios.telemetry.span_status import error_mask  # noqa: E402
from helios.vcl import VCLFlag  # noqa: E402,F401  flag-guard compliance

FILES = (
    "data.csv",
    "logs.csv",
    "traces.csv",
    "logts.csv",
    "tracets_err.csv",
    "tracets_lat.csv",
)


def main() -> int:
    out = Path(sys.argv[1])
    assert (
        Path(helios.__file__).resolve().is_relative_to(ROOT)
    ), "helios not from this checkout"
    manifest = json.loads((ROOT / "data/rcaeval/pool_manifest.json").read_text())
    order = manifest["case_order"]
    reader = CaptureReader(ROOT / "data/rcaeval/pool", seal_key=load_key())

    a = Counter()
    values = Counter()
    b = Counter()
    errors = Counter()
    for iid in order:
        try:
            res = reader.read(iid)
        except Exception as exc:
            errors[f"read:{type(exc).__name__}"] += 1
            continue
        a["windows_read"] += 1
        a["intact" if res.intact else "NOT_intact"] += 1
        w = res.window
        if w.p2_traces_path is None:
            a["no_traces"] += 1
        else:
            st = pq.read_table(
                ROOT / w.p2_traces_path, columns=["status_code"]
            ).to_pandas()
            vc = st["status_code"].astype(str).str.strip().str.upper().value_counts()
            values.update(vc.to_dict())
            distinct = pd.Series(vc.index, dtype="object")
            gpipe = {v: _is_error({"status_code": v}) for v in vc.index}
            digest = dict(zip(vc.index, error_mask(distinct).tolist(), strict=True))
            export = {v: is_error_span(v) for v in vc.index}
            a["distinct_values_where_rules_disagree"] += sum(
                not (gpipe[v] == digest[v] == export[v]) for v in vc.index
            )
            g_err = int(sum(n for v, n in vc.items() if gpipe[v]))
            e_err = int(sum(n for v, n in vc.items() if export[v]))
            a["windows_helios_sees_span_errors"] += g_err > 0
            a["windows_export_sees_span_errors"] += e_err > 0
            a["windows_disagree_on_error_count"] += g_err != e_err
            a["spans_total"] += int(vc.sum())
            a["spans_helios_error"] += g_err
            a["spans_export_error"] += e_err
        target = out / "export"
        try:
            counts = export_window(w, ROOT, target)
        except Exception as exc:
            errors[f"export:{type(exc).__name__}"] += 1
            continue
        b["exported"] += 1
        b["all_six_files"] += all((target / f).is_file() for f in FILES)
        for name in ("logts.csv", "tracets_err.csv", "tracets_lat.csv"):
            frame = pd.read_csv(target / name)
            has_series = frame.shape[1] > 1
            b[f"{name}:has_series"] += has_series
            b[f"{name}:rows_eq_grid"] += counts[name] == len(frame)
            if name != "tracets_lat.csv" and has_series:
                b[f"{name}:any_nonzero_error"] += (
                    bool(frame.drop(columns="time").fillna(0).to_numpy().sum() > 0)
                    if name == "tracets_err.csv"
                    else bool(
                        frame.filter(like="_logerror").fillna(0).to_numpy().sum() > 0
                    )
                )
        b["has_logs"] += w.p3_logs_path is not None
        b["has_traces"] += w.p2_traces_path is not None
        shutil.rmtree(target)

    print(f"export version: {EXPORT_VERSION}; pool cases in order: {len(order)}")
    print("== Check A: span status-code format ==")
    for k in sorted(a):
        print(f"  {k}: {a[k]}")
    print("  distinct status_code values (value: spans):")
    for v, n in values.most_common():
        print(f"    {v!r}: {n}")
    print("  rule: helios.telemetry.span_status (G-pipe, digests, export)")
    print(f"== Check B: rebuilt series ({EXPORT_VERSION}) ==")
    for k in sorted(b):
        print(f"  {k}: {b[k]}")
    print("== Failures ==")
    for k in sorted(errors):
        print(f"  {k}: {errors[k]}")
    if not errors:
        print("  none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
