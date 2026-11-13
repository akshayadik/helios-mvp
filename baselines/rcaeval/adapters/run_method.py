"""Run one RCAEval method on one exported case, inside a baseline container.

S4.8 (design docs/sprints/s4-product-eval-tooling/s4_8_baselines_design.md).
Runs under Python 3.12 (default image) and 3.8 (rcd image), so it uses no
newer syntax and imports nothing from HELIOS.

    python run_method.py /in /out

/in holds the files written by helios.baselines.export (RCAEval's layout:
data.csv, logs.csv, logts.csv, traces.csv, tracets_err.csv, tracets_lat.csv)
and job.json {method, seed, anomaly_time, dataset, length}. /out/result.json
receives {ranks, wall_ms, cpu_ms} or {error, traceback, wall_ms, cpu_ms}.

Data preparation follows RCAEval's main.py ``process()`` at commit 2fca61b:
drop the "time.1" column and ``*_latency-50``, replace infinities, forward
fill then zero fill, keep ``length * 60 // 2`` metric rows either side of the
anomaly time (``length * 4 // 2`` rows of the 15-second series), rename
``*_latency-90`` to ``*_latency``. Three departures, all recorded:
- ``sli`` is passed as None. main.py derives it from the case folder name,
  which carries the root-cause service; none of the five agreed methods reads
  it (checked at 2fca61b).
- TraceRCA receives the trace table and the anomaly time in microseconds
  (its own commented conversion); main.py passes it the metric table.
- TraceRCA (owner decision, deviation entry 88 item 10): spans of an
  operation with no span ending before the anomaly time are dropped before
  the call (``reference_spans_only``). RCAEval's tracerca.py looks up every
  anomalous operation's normal-period mean and raises KeyError when there is
  none; the operation is now skipped instead, and RCAEval's code is unchanged.

Timing covers reading the inputs and the method call (the analogue of HELIOS
reading its window); CPU time is ``time.process_time()``, as in HELIOS.
"""

from __future__ import annotations

import json
import os
import random as _random_module
import sys
import time
import traceback

HELIOS_ENABLE_BASELINES = True  # flag-guard: runs only inside the baseline images

_MS_PER_S = 1000
_US_PER_S = 1_000_000
METHODS = ("baro", "mmbaro", "mmrcd", "tracerca", "pdiagnose", "circa", "causalrca")
_MULTI_SOURCE = ("mmbaro", "mmrcd")


def seed_everything(seed):
    """The registered run seed for every generator a method may use."""
    _random_module.seed(seed)
    import numpy as np

    np.random.seed(seed % (2**32))
    try:
        import torch

        torch.manual_seed(seed)
    except ImportError:
        pass


def _read(path):
    import pandas as pd

    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def _window(df, anomaly_time, rows):
    import pandas as pd

    if df.shape[0] == 0:
        return df
    a = df[df["time"] < anomaly_time].tail(rows)
    b = df[df["time"] >= anomaly_time].head(rows)
    return pd.concat([a, b], ignore_index=True)


def prepare_metrics(df, anomaly_time, length):
    """main.py's metric preparation (see the module docstring)."""
    import numpy as np

    if "time.1" in df:
        df = df.drop(columns=["time.1"])
    df = df.loc[:, ~df.columns.str.endswith("_latency-50")]
    df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    df = _window(df, anomaly_time, length * 60 // 2)
    return df.rename(
        columns={
            c: c.replace("_latency-90", "_latency")
            for c in df.columns
            if c.endswith("_latency-90")
        }
    )


def reference_spans_only(span_df, anomaly_time_us):
    """Keep the spans of operations that have at least one normal-period span
    (one that ends before the anomaly time), with TraceRCA's operation key."""
    if span_df.shape[0] == 0:
        return span_df
    method = span_df["methodName"].fillna(span_df["operationName"])
    operation = span_df["serviceName"] + "_" + method
    normal = span_df["startTime"] + span_df["duration"] < anomaly_time_us
    known = set(operation[normal])
    return span_df[operation.isin(known)].reset_index(drop=True)


def call_method(method, inputs, job):
    """Call one method with main.py's arguments; return its ranks."""
    t = int(job["anomaly_time"])
    dataset = job["dataset"]
    length = int(job.get("length", 20))
    seed = int(job["seed"])
    metric = prepare_metrics(inputs["metric"], t, length)
    common = {
        "dataset": dataset,
        "anomalies": None,
        "dk_select_useful": False,
        "sli": None,
        "verbose": False,
        "n_iter": len(metric.columns) - 1,
    }
    if method in _MULTI_SOURCE:
        rows = length * 4 // 2
        data = {
            "metric": metric.copy(deep=True),
            "logts": _window(inputs["logts"], t, rows),
            "tracets_err": _window(inputs["tracets_err"], t, rows),
            "tracets_lat": _window(inputs["tracets_lat"], t, rows),
        }
        if method == "mmbaro":
            from RCAEval.e2e import mmbaro

            return mmbaro(data, t, **common)["ranks"]
        from RCAEval.e2e import mmrcd

        return mmrcd(data, t, seed=seed, **common)["ranks"]
    if method == "tracerca":
        from RCAEval.e2e import tracerca

        t_us = t * _US_PER_S
        spans = reference_spans_only(inputs["traces"], t_us)
        return tracerca(spans, t_us, dataset=dataset)["ranks"]
    if method == "pdiagnose":
        from pdiagnose_adapter import pdiagnose

        data = {"metric": metric, "logs": inputs["logs"], "traces": inputs["traces"]}
        return pdiagnose(data, t, dataset=dataset)["ranks"]
    if method == "baro":
        from RCAEval.e2e import baro

        return baro(metric, t, **common)["ranks"]
    if method == "circa":
        from RCAEval.e2e import circa

        return circa(metric, t, **common)["ranks"]
    if method == "causalrca":
        from RCAEval.e2e import causalrca

        return causalrca(metric, t, **common)["ranks"]
    raise ValueError("unknown method " + repr(method))


def main(argv):
    in_dir, out_dir = argv[1], argv[2]
    with open(os.path.join(in_dir, "job.json")) as f:
        job = json.load(f)
    method = job["method"]
    if method not in METHODS:
        raise SystemExit("unknown method " + repr(method))
    seed_everything(int(job["seed"]))
    wall, cpu = time.perf_counter(), time.process_time()
    out = {}
    try:
        inputs = {
            "metric": _read(os.path.join(in_dir, "data.csv")),
            "logs": _read(os.path.join(in_dir, "logs.csv")),
            "logts": _read(os.path.join(in_dir, "logts.csv")),
            "traces": _read(os.path.join(in_dir, "traces.csv")),
            "tracets_err": _read(os.path.join(in_dir, "tracets_err.csv")),
            "tracets_lat": _read(os.path.join(in_dir, "tracets_lat.csv")),
        }
        out["ranks"] = [str(r) for r in call_method(method, inputs, job)]
    except Exception as exc:  # a method failure is data, not a crash
        out["error"] = type(exc).__name__ + ": " + str(exc)[:300]
        out["traceback"] = traceback.format_exc()[-4000:]
    out["wall_ms"] = (time.perf_counter() - wall) * _MS_PER_S
    out["cpu_ms"] = (time.process_time() - cpu) * _MS_PER_S
    with open(os.path.join(out_dir, "result.json"), "w") as f:
        json.dump(out, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
