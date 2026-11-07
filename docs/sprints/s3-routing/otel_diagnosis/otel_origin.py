"""Where errors originate, and what the fused list ranked, for the misses (scratch)."""

import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

HELIOS_ENABLE_OTEL_DIAGNOSIS = True  # scratch analysis
rows = {r["case"]: r for r in json.loads(Path(sys.argv[1]).read_text())}
truth = json.loads(Path("data/otel/ground_truth_build_v3.json").read_text())["cases"]
by_case = {lab["case"].split("/", 1)[1]: inc for inc, lab in truth.items()}


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


for case, r in rows.items():
    if r["hit"] and not case.startswith("recommendation"):
        continue
    inc = by_case[case]
    lab = truth[inc]
    t = pd.read_parquet(f"data/otel/build_v3/{inc}/p2_traces.parquet")
    t = t[t.start_time_us / 1e6 >= ts(lab["inject_time"])]
    err = t[t.status_code == "ERROR"]
    child_err = set(err.parent_span_id)
    origin = err[~err.span_id.isin(child_err)]
    ops = Counter(
        zip(origin.service_name, origin.operation_name, strict=False)
    ).most_common(3)
    by_id = t.set_index("span_id")
    # for the root's error spans: which service are their erroring children in?
    root_err = err[err.service_name == lab["root_cause_service"]]
    kids = err[err.parent_span_id.isin(set(root_err.span_id))]
    print(
        f"{case[:34]:34s} {'Y' if r['hit'] else 'n'} fused_top3={r['fused_top3']} origin={ops} root_err_children_svc={dict(Counter(kids.service_name).most_common(3))}"
    )
