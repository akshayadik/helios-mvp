"""How often each channel ranks the root first, per fault type (scratch)."""

import json
import sys
from collections import defaultdict
from pathlib import Path

HELIOS_ENABLE_OTEL_DIAGNOSIS = True  # scratch analysis
rows = json.loads(Path(sys.argv[1]).read_text())
CH = [
    "error_origin",
    "error_spans",
    "error_calls_metric",
    "memory",
    "cpu",
    "span_p90_ms",
    "error_logs",
]
agg = defaultdict(lambda: defaultdict(int))
for r in rows:
    for c in CH:
        v = r["visibility"][c]
        top = v["rank"] == 1 and (v["shift"] or 0) > 0
        agg[r["fault"]][c] += top
print("fault".ljust(28), " ".join(c[:10].rjust(11) for c in CH))
for f in sorted(agg):
    print(f.ljust(28), " ".join(str(agg[f][c]).rjust(11) for c in CH))
print("all".ljust(28), " ".join(str(sum(agg[f][c] for f in agg)).rjust(11) for c in CH))
