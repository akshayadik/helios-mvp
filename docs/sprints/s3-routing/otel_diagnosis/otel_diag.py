"""OTel build miss diagnosis (scratch, read-only, exploratory).

Per case: the trigger, each pipeline's rank of the true root, the fused rank;
and how visible the fault is in the raw data. Visibility, per in-scope service
and channel, is the shift from the pre-injection baseline to the fault period
in 60 s buckets:
- counts (spans, error spans, error-origin spans, error/warn logs, error calls):
  (fault mean - baseline mean) / sqrt(baseline mean + 1), a Poisson-scaled shift;
- levels (span p90 latency, CPU, memory, span mean latency):
  (fault median - baseline median) / (1.4826 MAD + 1% of |baseline median| + tiny).
The root's shift and its rank among in-scope services (by shift, descending)
say whether the fault shows in that channel and whether it stands out.
"""

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path.cwd()))
from helios.telemetry.scope import in_scope

HELIOS_ENABLE_OTEL_DIAGNOSIS = True  # scratch analysis, not a component

BUCKET = 60
TINY = 1e-9
REL = 1e-2  # 1% of the baseline level as a floor on the scale
ROOT = Path("data/otel/build_v3")
coe = Path(sys.argv[1])
out_json = Path(sys.argv[2])
truth = json.loads(Path("data/otel/ground_truth_build_v3.json").read_text())["cases"]


def ts(iso: str) -> float:
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def step(entry, sid):
    return next(s for s in entry["steps"] if s["id"] == sid)


def rank(ranked, root):
    ranked = [s for s in ranked if in_scope(s)]
    return ranked.index(root) + 1 if root in ranked else None


def buckets(times, start, inject, end):
    edges_b = np.arange(start, inject + TINY, BUCKET)
    edges_f = np.arange(inject, end + TINY, BUCKET)
    b = np.histogram(times, edges_b)[0] if len(edges_b) > 1 else np.array([0])
    f = np.histogram(times, edges_f)[0] if len(edges_f) > 1 else np.array([0])
    return b, f


def count_shift(b, f):
    mb = float(np.mean(b)) if len(b) else 0
    mf = float(np.mean(f)) if len(f) else 0
    return (mf - mb) / np.sqrt(mb + 1), mb, mf


def level_shift(base_vals, fault_vals):
    if len(base_vals) == 0 or len(fault_vals) == 0:
        return None, None, None
    mb = float(np.median(base_vals))
    mf = float(np.median(fault_vals))
    mad = float(np.median(np.abs(np.asarray(base_vals) - mb)))
    return (mf - mb) / (1.4826 * mad + abs(mb) * REL + TINY), mb, mf


def bucket_stat(g, tcol, vcol, start, lo, hi, how):
    sel = g[(g[tcol] >= lo) & (g[tcol] < hi)]
    if sel.empty:
        return np.array([])
    grp = sel.groupby(((sel[tcol] - start) // BUCKET).astype(int))[vcol]
    return (grp.quantile(0.9) if how == "p90" else grp.median()).to_numpy()


def standing(shifts, root):
    vals = {s: v[0] for s, v in shifts.items() if in_scope(s) and v[0] is not None}
    if root not in vals:
        return {"shift": None, "rank": None, "of": len(vals)}
    order = sorted(vals, key=lambda s: -vals[s])
    r = shifts[root]
    return {
        "shift": round(float(r[0]), 2),
        "rank": order.index(root) + 1,
        "of": len(vals),
        "before": None if r[1] is None else round(r[1], 3),
        "after": None if r[2] is None else round(r[2], 3),
    }


def visibility(inc, lab):
    d = ROOT / inc
    start, inject, end = (
        ts(lab["window_start"]),
        ts(lab["inject_time"]),
        ts(lab["window_end"]),
    )
    root = lab["root_cause_service"]
    out = {}
    t = pd.read_parquet(d / "p2_traces.parquet")
    t["t"] = t.start_time_us / 1e6
    t["err"] = t.status_code == "ERROR"
    child_err = set(t.loc[t.err, "parent_span_id"])
    t["origin"] = t.err & ~t.span_id.isin(child_err)
    for name, mask in (
        ("spans", None),
        ("error_spans", "err"),
        ("error_origin", "origin"),
    ):
        shifts = {}
        for svc, g in t.groupby("service_name"):
            times = g.t if mask is None else g.loc[g[mask], "t"]
            shifts[svc] = count_shift(*buckets(times.to_numpy(), start, inject, end))
        out[name] = standing(shifts, root)
    t["dur_ms"] = t.duration_us / 1e3
    out["span_p90_ms"] = standing(
        {
            svc: level_shift(
                bucket_stat(g, "t", "dur_ms", start, start, inject, "p90"),
                bucket_stat(g, "t", "dur_ms", start, inject, end + TINY, "p90"),
            )
            for svc, g in t.groupby("service_name")
        },
        root,
    )
    lg = pd.read_parquet(d / "p3_logs.parquet")
    lg["t"] = lg.timestamp.map(ts)
    bad = lg[lg.severity.str.upper().isin(["ERROR", "WARN", "WARNING", "FATAL"])]
    shifts = {}
    for svc in lg.service_name.unique():
        g = bad[bad.service_name == svc]
        shifts[svc] = count_shift(*buckets(g.t.to_numpy(), start, inject, end))
    out["error_logs"] = standing(shifts, root)
    m = pd.read_parquet(d / "p1_metrics.parquet")
    m["service"] = m["labels"].map(lambda s: json.loads(s).get("service_name"))
    for metric, key in (
        ("container_cpu_utilization_ratio", "cpu"),
        ("container_memory_usage_total_bytes", "memory"),
        ("span_mean_latency_milliseconds", "span_mean_latency"),
    ):
        mm = m[m.metric_name == metric]
        out[key] = standing(
            {
                svc: level_shift(
                    bucket_stat(
                        g, "timestamp", "value", start, start, inject, "median"
                    ),
                    bucket_stat(
                        g, "timestamp", "value", start, inject, end + TINY, "median"
                    ),
                )
                for svc, g in mm.groupby("service")
            },
            root,
        )
    ec = m[m.metric_name == "span_error_calls_total"].sort_values("timestamp")
    shifts = {}
    for svc, g in ec.groupby("service"):
        g = g.drop_duplicates("timestamp")
        inc_ = g.value.diff().clip(lower=0).fillna(0)
        b = inc_[g.timestamp < inject].to_numpy()
        f = inc_[g.timestamp >= inject].to_numpy()
        shifts[svc] = count_shift(b, f) if len(f) else (None, None, None)
    out["error_calls_metric"] = standing(shifts, root)
    out["error_calls_metric"]["series"] = root in shifts
    return out


rows = []
for line in coe.read_text().splitlines():
    e = json.loads(line)
    inc = e["incident_id"]
    lab = truth[inc]
    root = lab["root_cause_service"]
    T = step(e, "T")
    row = {
        "case": lab["case"].split("/", 1)[1],
        "fault": lab["fault"],
        "root": root,
        "trigger": T["source"],
        "root_in_suspects": root in T["suspects"],
        "signal": T.get("signal"),
        "dpipe": rank(step(e, "P:dpipe")["ranked"], root),
        "gpipe": rank(step(e, "P:gpipe")["ranked"], root),
        "lpipe": rank(step(e, "P:lpipe")["ranked"], root),
        "fused": rank(step(e, "F")["ranked"], root),
        "fused_top3": [s for s in step(e, "F")["ranked"] if in_scope(s)][:3],
        "state": step(e, "F")["state"],
        "visibility": visibility(inc, lab),
    }
    row["hit"] = row["fused"] is not None and row["fused"] <= 3
    rows.append(row)

rows.sort(key=lambda r: r["case"])
out_json.write_text(json.dumps(rows, indent=1))
print(f"fused HR@3 {sum(r['hit'] for r in rows)}/{len(rows)}")
by_fault = defaultdict(list)
for r in rows:
    by_fault[r["fault"]].append(r)
for f, rs in sorted(by_fault.items()):
    print(
        f"{f:28s} hits {sum(r['hit'] for r in rs)}/7  D {sum((r['dpipe'] or 99) <= 3 for r in rs)} "
        f"G {sum((r['gpipe'] or 99) <= 3 for r in rs)} L {sum((r['lpipe'] or 99) <= 3 for r in rs)}  "
        f"fallback {sum(r['trigger'] == 'fallback' for r in rs)}  root-in-suspects {sum(r['root_in_suspects'] for r in rs)}"
    )
