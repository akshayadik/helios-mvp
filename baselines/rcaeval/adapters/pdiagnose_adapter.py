"""PDiagnose (B4) as an RCAEval-style function: a faithful port of
``RCAEval/e2e/pdiagnose.py`` ``main()`` at commit 2fca61b (S4.8, design B-d).

Kept from the script: ALPHA = 5; a metric scores the number of anomalous-period
points at or above mean + 3 sigma of its normal period; a container scores the
number of its log lines (whole window, as in the script) whose message contains
"error" or "fail" (case-sensitive regex ``error|fail``); a service scores the
number of its anomalous-period spans whose duration (ms) is at or above the
operation's normal mean + 3 sigma; each count is weighted by ALPHA and summed
per service; services are ranked by score, highest first. The script's unused
constants T and K and its unused logts input are dropped.

Departures (recorded in the deviation entry):
1. inputs come from the ``data`` dictionary, not hard-coded case paths, and the
   ranking is returned (service names only) instead of printed;
2. metric names are split at the first "_" only (the script's
   ``s, m = k.split("_")`` raises on a metric name with a second "_");
3. a service seen only in logs or traces starts at score zero instead of
   raising KeyError;
4. the script's ``frontendservice`` -> ``frontend`` rename is dropped: inputs
   already carry canonical service names;
5. ties are broken by service name (the script keeps dict insertion order);
6. a span operation with no normal-period spans has no reference, so its
   anomalous spans are not counted (the script raises KeyError).
"""

from __future__ import annotations

HELIOS_ENABLE_BASELINES = True  # flag-guard: runs only inside the baseline images

ALPHA = 5
_US_PER_S = 1_000_000
_MS_PER_US = 1000


def _operation_slo(span_df):
    out = {}
    for op in span_df["operation"].dropna().unique():
        durations = span_df[span_df["operation"] == op]["duration"]
        out[op] = {
            "mean": round(durations.mean() / _MS_PER_US, 2),
            "std": round(durations.std() / _MS_PER_US, 2),
        }
    return out


def pdiagnose(data, inject_time, dataset=None, **kwargs):
    metric_df = data["metric"]
    log_df = data["logs"]
    span_df = data["traces"]
    scores = {}

    # metrics
    normal = metric_df[metric_df["time"] < inject_time]
    anomal = metric_df[metric_df["time"] >= inject_time]
    for m in [c for c in metric_df.columns if "time" not in c]:
        threshold = normal[m].mean() + 3 * normal[m].std()
        q = len(anomal[anomal[m] >= threshold])
        service = m.split("_", 1)[0]
        scores[service] = scores.get(service, 0) + ALPHA * q

    # logs (the whole window, as in the script)
    if log_df.shape[0] > 0:
        for c in log_df["container_name"].unique():
            mask = (log_df["container_name"] == c) & (
                log_df["message"].astype(str).str.contains("error|fail")
            )
            scores[c] = scores.get(c, 0) + ALPHA * int(mask.sum())

    # traces
    if span_df.shape[0] > 0:
        span_df = span_df.copy()
        span_df["methodName"] = span_df["methodName"].fillna(span_df["operationName"])
        span_df["operation"] = span_df["serviceName"] + "_" + span_df["methodName"]
        t_us = inject_time * _US_PER_S
        end = span_df["startTime"] + span_df["duration"]
        normal_spans = span_df[end < t_us]
        anomal_spans = span_df[end >= t_us].copy()
        slo = _operation_slo(normal_spans)
        known = anomal_spans["operation"].isin(list(slo))
        anomal_spans = anomal_spans[known]
        mean = anomal_spans["operation"].map(lambda op: slo[op]["mean"])
        std = anomal_spans["operation"].map(lambda op: slo[op]["std"])
        abnormal = anomal_spans["duration"] / _MS_PER_US >= mean + 3 * std
        for s in span_df["serviceName"].unique():
            n = int(abnormal[anomal_spans["serviceName"] == s].sum())
            scores[s] = scores.get(s, 0) + ALPHA * n

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"ranks": [k for k, _ in ranked]}
