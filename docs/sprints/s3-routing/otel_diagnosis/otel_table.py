"""Print the per-case visibility table for the diagnosis (scratch)."""

import json
import sys
from pathlib import Path

rows = json.loads(Path(sys.argv[1]).read_text())
CH = [
    "error_spans",
    "error_origin",
    "error_logs",
    "error_calls_metric",
    "span_p90_ms",
    "span_mean_latency",
    "spans",
    "cpu",
    "memory",
]
short = {
    "error_spans": "errSp",
    "error_origin": "errOrig",
    "error_logs": "errLog",
    "error_calls_metric": "errMet",
    "span_p90_ms": "p90",
    "span_mean_latency": "latMet",
    "spans": "calls",
    "cpu": "cpu",
    "memory": "mem",
}
print("case | hit | D G L F | trig | " + " | ".join(short[c] for c in CH))
for r in rows:
    if r["fault"] not in {
        "adFailure",
        "emailMemoryLeak",
        "paymentFailure",
        "productCatalogFailure",
        "recommendationCacheFailure",
    }:
        continue
    v = r["visibility"]
    cells = []
    for c in CH:
        x = v[c]
        cells.append("-" if x["shift"] is None else f"{x['shift']:+.1f}#{x['rank']}")
    rk = " ".join(str(r[k] or "-") for k in ("dpipe", "gpipe", "lpipe", "fused"))
    print(
        f"{r['case'][:38]:38s} | {'Y' if r['hit'] else 'n'} | {rk} | {r['trigger'][:4]} | "
        + " | ".join(cells)
    )
