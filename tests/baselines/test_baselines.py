"""S4.8 baselines: export (B-a), mapping (B-c), executor and failures (B-f),
scoring and CpR (B-e), the PDiagnose port (B-d), with hand-computed values."""

from __future__ import annotations

import csv
import importlib
import json
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import pytest

from bin.log_exclusion import ExclusionLedger
from helios.baselines.container import (
    ADAPTER_DIR,
    BaselineConfigError,
    BaselineTimeoutError,
    Limits,
    adapter_digest,
)
from helios.baselines.executor import (
    METHODS,
    TRIGGER_SUFFIX,
    BaselineExecutor,
    services_from_ranks,
    source_name,
)
from helios.baselines.export import export_window, is_error_log, is_error_span
from helios.evaluation.cost import PriceBook
from helios.evaluation.run_metrics import BASELINE_STATE, score_run_metrics
from helios.evaluation.scoring import Corpus, GroundTruth, score_store
from helios.research.analysis_plan import BASELINES
from helios.store.result_store import ResultStore
from helios.telemetry.pool_lock import PoolLockedError
from helios.telemetry.trigger import ProvisionalParametersError
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.baselines.fixtures import KEY, START, capture, window_of

if TYPE_CHECKING:
    from collections.abc import Iterator

GRID0 = 1_699_999_995  # START floored to the 15-second grid
US = 1_000_000


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


# ── export (B-a) ─────────────────────────────────────────────────────────────


def test_export_writes_rcaeval_layout(tmp_path: Path) -> None:
    inc = capture(tmp_path, "inc-1")
    out = tmp_path / "out"
    counts = export_window(window_of(inc), tmp_path, out)
    assert counts == {
        "data.csv": 8,
        "logs.csv": 3,
        "traces.csv": 3,
        "logts.csv": 8,
        "tracets_err.csv": 8,
        "tracets_lat.csv": 8,
    }
    data = _csv(out / "data.csv")
    assert list(data[0]) == ["time", "ad_cpu", "cart_cpu"]
    # Two host series per name -> the mean: cart (1+i + 3+i)/2, ad (10+i + 12+i)/2.
    assert [float(r["cart_cpu"]) for r in data] == [2 + i for i in range(8)]
    assert float(data[3]["ad_cpu"]) == 14
    assert int(data[0]["time"]) == START
    logs = _csv(out / "logs.csv")
    assert logs[1]["container_name"] == "cart"
    assert int(logs[0]["timestamp"]) == (START + 3) * 1_000_000_000
    assert logs[2]["level"] == "error"
    traces = _csv(out / "traces.csv")
    assert traces[0]["methodName"] == traces[0]["operationName"] == "GetCart"
    assert int(traces[2]["startTime"]) == (START + 20) * US


def test_derived_fifteen_second_series(tmp_path: Path) -> None:
    out = tmp_path / "out"
    export_window(window_of(capture(tmp_path, "inc-1")), tmp_path, out)
    logts = {int(r["time"]): r for r in _csv(out / "logts.csv")}
    assert min(logts) == GRID0 and len(logts) == 8
    # Logs at START+3 and START+4 fall in bucket GRID0 (2 lines, "FAILED" is an
    # error); START+31 in GRID0 + 30 (one ERROR line).
    assert logts[GRID0]["cart_log"] == "2" and logts[GRID0]["cart_logerror"] == "1"
    assert logts[GRID0 + 30]["ad_log"] == "1"
    assert logts[GRID0 + 30]["ad_logerror"] == "1"
    assert logts[GRID0 + 15]["cart_log"] == "0"
    err = {int(r["time"]): r for r in _csv(out / "tracets_err.csv")}
    lat = {int(r["time"]): r for r in _csv(out / "tracets_lat.csv")}
    # Spans: START+1 cart UNSET 2 ms, START+2 ad ERROR 4 ms, START+20 cart 503 6 ms.
    assert err[GRID0]["cart_GetCart"] == "0" and err[GRID0 + 15]["cart_GetCart"] == "1"
    assert err[GRID0]["ad_GetAd"] == "1"
    assert float(lat[GRID0]["cart_GetCart"]) == 2
    assert float(lat[GRID0 + 15]["cart_GetCart"]) == 6
    assert lat[GRID0 + 30]["cart_GetCart"] == ""  # no span: left empty


def test_error_rules() -> None:
    assert is_error_span("ERROR") and is_error_span("STATUS_CODE_ERROR")
    assert is_error_span("500") and not is_error_span("200")
    assert not is_error_span("UNSET") and not is_error_span("OK")
    assert is_error_log("fatal", "x") and is_error_log("", "upstream Error")
    assert not is_error_log("INFO", "all good")


def test_export_of_a_metrics_only_window(tmp_path: Path) -> None:
    inc = capture(tmp_path, "inc-1")
    window = window_of(inc).model_copy(
        update={"p2_traces_path": None, "p3_logs_path": None}
    )
    counts = export_window(window, tmp_path, tmp_path / "out")
    assert counts["logs.csv"] == 0 and "tracets_err.csv" not in counts
    assert list(_csv(tmp_path / "out" / "logts.csv")[0]) == ["time"]


# ── mapping (B-c) ────────────────────────────────────────────────────────────


def test_services_from_metric_ranks() -> None:
    ranks = ["cart_cpu", "cart_mem", "ad_latency", "redis_mem", "ad_cpu", "cart"]
    assert services_from_ranks(ranks) == ["cart", "ad", "redis"]
    assert source_name("PDiagnose", "inject") == "PDiagnose"
    assert source_name("PDiagnose", "trigger") == "PDiagnose" + TRIGGER_SUFFIX
    assert set(BASELINES) <= set(METHODS)


# ── executor (B-a, B-b, B-f, B-i) ────────────────────────────────────────────


class StubRunner:
    def __init__(self, result: dict[str, Any] | Exception) -> None:
        self.result = result
        self.jobs: list[dict[str, Any]] = []
        self.files: list[list[str]] = []

    def check_image(self, env: str) -> str:
        return f"sha256:{env}"

    def run(
        self, env: str, in_dir: Path, out_dir: Path, name: str, limits: Limits
    ) -> dict[str, Any]:
        self.jobs.append(json.loads((in_dir / "job.json").read_text()))
        self.files.append(sorted(p.name for p in in_dir.iterdir()))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _ledger(tmp_path: Path) -> ExclusionLedger:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "excl.jsonl"
    path.touch()
    ledger = ExclusionLedger(key=KEY, log_path=path)
    ledger.init_anchor()
    return ledger


def _executor(
    tmp_path: Path,
    runner: StubRunner,
    *,
    baseline: str = BASELINES[2],
    anomaly: str = "inject",
    **kw: Any,
) -> tuple[BaselineExecutor, ExclusionLedger]:
    ledger = _ledger(tmp_path)
    ex = BaselineExecutor(
        baseline,
        anomaly=anomaly,
        captures_dir=tmp_path / "caps",
        repo_root=tmp_path,
        db_path=tmp_path / "r.duckdb",
        reconciliation_path=tmp_path / "rec" / "r.jsonl",
        exclusion_ledger=ledger,
        hmac_key=KEY,
        runner=runner,
        inject_times=lambda: {"inc-1": START + 60.9},
        dataset_for={"inc-1": "re2-tt"},
        work_dir=tmp_path,
        **kw,
    )
    return ex, ledger


def _entries(ledger: ExclusionLedger) -> list[dict[str, Any]]:
    path = ledger.anchor_path.with_name("excl.jsonl")
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_executor_passes_and_stores_the_mapped_ranking(tmp_path: Path) -> None:
    capture(tmp_path / "caps", "inc-1")
    ranks = ["cart_cpu", "ad_cpu", "cart_mem"]
    runner = StubRunner({"ranks": ranks, "wall_ms": 1200, "cpu_ms": 2000})
    ex, ledger = _executor(tmp_path, runner)
    ex.prepare()
    out = ex.run_incident("inc-1", "run-1", {"seed": "10000007"})
    assert (out.outcome, out.gate_check) == ("passed", None)
    (job,) = runner.jobs
    assert job == {
        "method": "baro",
        "seed": 10000007,
        "anomaly_time": START + 60,  # the injection time, whole seconds
        "dataset": "re2-tt",
        "length": 20,
    }
    assert "data.csv" in runner.files[0] and "tracets_lat.csv" in runner.files[0]
    store = ResultStore(tmp_path / "r.duckdb")
    (row,) = store.fetch_all_baseline_rows()
    assert row["ranked"] == ["cart", "ad"]
    assert row["raw_ranks"] == ranks
    assert (row["source"], row["image_digest"], row["cpus"]) == (
        BASELINES[2],
        "sha256:default",
        8,
    )
    assert store.fetch_baseline("run-1") == row and store.fetch_baseline("x") is None
    store.close()
    assert ex.discard_run("run-1") == 1
    assert _entries(ledger) == []
    assert len(ex.config_hash) == 64


def test_method_error_and_timeout_are_exclusions(tmp_path: Path) -> None:
    capture(tmp_path / "caps", "inc-1")
    err = StubRunner({"error": "KeyError: 'op'", "wall_ms": 5, "cpu_ms": 5})
    ex, ledger = _executor(tmp_path, err)
    out = ex.run_incident("inc-1", "run-1", {"seed": "1"})
    assert (out.outcome, out.gate_check) == ("excluded", "baseline_error")
    timeout = StubRunner(BaselineTimeoutError("no result within 1800 s"))
    ex2 = BaselineExecutor(
        BASELINES[4],
        anomaly="inject",
        captures_dir=tmp_path / "caps",
        repo_root=tmp_path,
        db_path=tmp_path / "r.duckdb",
        reconciliation_path=tmp_path / "rec" / "r2.jsonl",
        exclusion_ledger=ledger,
        hmac_key=KEY,
        runner=timeout,
        inject_times=lambda: {"inc-1": START + 60},
        dataset_for={},
    )
    assert ex2.run_incident("inc-1", "run-2").gate_check == "baseline_timeout"
    first, second = _entries(ledger)
    assert first["reason"] == "KeyError: 'op'" and first["baseline"] == BASELINES[2]
    assert second["gate_check"] == "baseline_timeout"
    assert second["snapshot_hash"] != "UNKNOWN"
    assert timeout.jobs[0]["method"] == "mmrcd"
    assert timeout.jobs[0]["dataset"] == "re2-ob"  # no app: OTel's default


def test_unsealed_capture_and_infrastructure_errors(tmp_path: Path) -> None:
    capture(tmp_path / "caps", "inc-1", seal=False)
    ok = StubRunner({"ranks": [], "wall_ms": 1, "cpu_ms": 1})
    ex, ledger = _executor(tmp_path, ok)
    assert ex.run_incident("inc-1", "run-1").gate_check == "capture_seal_invalid"
    assert _entries(ledger)[0]["snapshot_hash"] == "UNKNOWN"
    other = tmp_path / "x"
    capture(other / "caps", "inc-1")
    ex2, _ = _executor(other, StubRunner(ConnectionError("docker down")))
    with pytest.raises(ConnectionError):  # the campaign retries it
        ex2.run_incident("inc-1", "run-2")


def test_anomaly_time_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    capture(tmp_path / "caps", "inc-1")
    runner = StubRunner({"ranks": ["ad_cpu"], "wall_ms": 1, "cpu_ms": 1})

    class Params:
        provisional = False

    class Trigger:
        trigger_time_s = START + 45.4

    monkeypatch.setattr(
        "helios.baselines.executor.detect", lambda window, params: Trigger()
    )
    ex, _ = _executor(tmp_path, runner, anomaly="trigger", detector_params=Params())
    assert ex.source.endswith(TRIGGER_SUFFIX)
    ex.run_incident("inc-1", "run-1")
    assert runner.jobs[0]["anomaly_time"] == START + 45
    window = window_of(tmp_path / "caps" / "inc-1")
    Params.provisional = True
    confirmatory = window.model_copy(update={"evaluation_phase": "confirmatory"})
    with pytest.raises(ProvisionalParametersError):
        ex._anomaly_time("inc-1", confirmatory)
    ex_inject, _ = _executor(tmp_path / "y", runner)
    with pytest.raises(BaselineConfigError):
        ex_inject._anomaly_time("other", window)
    with pytest.raises(ValueError, match="unknown baseline"):
        _executor(tmp_path / "z", runner, baseline="nope")
    with pytest.raises(ValueError, match="anomaly source"):
        _executor(tmp_path / "w", runner, anomaly="later")


def test_adapter_digest_tracks_the_adapter_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    first = adapter_digest(tmp_path)
    (tmp_path / "a.py").write_text("x = 2\n")
    assert adapter_digest(tmp_path) != first
    assert len(adapter_digest()) == 64


# ── scoring and CpR (B-e) ────────────────────────────────────────────────────

BOOK = PriceBook(
    version="fixture",
    currency="X",
    provider="fixture",
    region="-",
    cpu_machine="-",
    gpu_machine="-",
    storage_tier="-",
    token_prompt_per_million=2,
    token_completion_per_million=4,
    cpu_per_vcpu_hour=36,
    gpu_per_hour=72,
    storage_per_gib_month=3,
    storage_retention_months=2,
    human_per_hour=60,
    human_review_minutes=10,
    opportunity_per_minute=2,
    ttcd_censor_s=1800,
    unverified=(),
    digest="book-digest",
)
GT = GroundTruth(
    corpus=Corpus.BUILD,
    labels={"inc-1": "cart", "inc-2": "cart"},
    digest="g",
    stem=False,
)


def _baseline_row(run: str, incident: str, ranked: list[str]) -> dict[str, Any]:
    return {
        "run_id": run,
        "incident_id": incident,
        "baseline": BASELINES[0],
        "source": BASELINES[0],
        "method": "mmbaro",
        "config_hash": "c" * 64,
        "anomaly_source": "inject",
        "anomaly_time_s": START,
        "ranked": ranked,
        "raw_ranks": [f"{s}_cpu" for s in ranked],
        "wall_ms": 12_000,
        "cpu_ms": 2_000,
        "cpus": 8,
        "run_seed": 7,
        "image_digest": "sha256:x",
        "evaluation_phase": "exploratory",
        "snapshot_hash": "s" * 64,
    }


def test_baseline_rows_are_scored_and_costed(tmp_path: Path) -> None:
    store = ResultStore(tmp_path / "r.duckdb")
    store.insert_baseline(_baseline_row("b1", "inc-1", ["cart", "ad"]))
    store.insert_baseline(_baseline_row("b2", "inc-2", ["ad", "cart"]))
    store.insert_baseline(_baseline_row("b3", "inc-9", ["ad"]))  # no label
    report = score_store(store, GT)
    assert report.unlabelled == 1
    scores = {r["run_id"]: r for r in store.fetch_scores()}
    assert scores["b1"]["source"] == BASELINES[0]
    assert scores["b1"]["variant_config_hash"] is None
    assert scores["b1"]["list_kind"] == "fused" and scores["b1"]["hr_at_3"] == 1
    assert scores["b2"]["ground_truth_rank"] == 2
    gib = 2**30
    runs = score_run_metrics(
        store, GT, BOOK, storage_bytes={"inc-1": gib, "inc-2": gib, "inc-9": 1}
    )
    assert runs.unlabelled == 1
    rows = {r["run_id"]: r for r in runs.rows}
    b1, b2 = rows["b1"], rows["b2"]
    # b1: right at 12 s. CPU 2 s x 0.01 = 0.02; storage 1 GiB x 6 = 6;
    # human 10 (always, B-e (a)); opportunity 12/60 x 2 = 0.4 -> 16.42.
    assert b1["state"] == BASELINE_STATE and b1["requests_human"] is True
    assert (b1["ttcd_s"], b1["ttcd_censored"], b1["ttt_ms"]) == (12, False, 12_000)
    assert b1["cpr_total"] == pytest.approx(16.42, abs=1e-9)
    assert b1["log_cpr"] == pytest.approx(math.log(16.42), abs=1e-9)
    # b2: top-1 wrong -> censored at 1,800 s: opportunity 60 -> 76.02.
    assert b2["ttcd_censored"] is True
    assert b2["cpr_total"] == pytest.approx(76.02, abs=1e-9)
    assert b1["llm_consulted"] is False and b1["h_fact"] is None
    store.close()


def test_confirmatory_baseline_rows_wait_for_the_freeze(tmp_path: Path) -> None:
    store = ResultStore(tmp_path / "r.duckdb")
    row = _baseline_row("b1", "inc-1", ["cart"]) | {"evaluation_phase": "confirmatory"}
    store.insert_baseline(row)
    with pytest.raises(PoolLockedError):
        score_store(store, GT, frozen=lambda: False)
    with pytest.raises(PoolLockedError):
        score_run_metrics(
            store, GT, BOOK, storage_bytes={"inc-1": 1}, frozen=lambda: False
        )
    store.close()


# ── the PDiagnose port (B-d) and the wrapper's data preparation ──────────────


@pytest.fixture
def adapters() -> Iterator[tuple[Any, Any]]:
    sys.path.insert(0, str(ADAPTER_DIR))
    try:
        yield (
            importlib.import_module("pdiagnose_adapter"),
            importlib.import_module("run_method"),
        )
    finally:
        sys.path.remove(str(ADAPTER_DIR))


def test_pdiagnose_port_scores_by_hand(adapters: tuple[Any, Any]) -> None:
    pd_mod, _ = adapters
    metric = pd.DataFrame(
        {
            "time": list(range(20)),
            # cart_cpu: normal alternates 0 and 1 (mean and sd both near a
            # half); the anomalous 9s exceed mean + 3 sd at 3 points.
            "cart_cpu": [i % 2 for i in range(10)] + [9, 9, 9] + [0] * 7,
            "ad_cpu": [1] * 20,  # flat: sd 0, so all 10 anomalous points count
            "ad_net_rx": [1] * 20,  # a second "_": the script would raise
        }
    )
    logs = pd.DataFrame(
        {
            "container_name": ["cart", "redis", "redis"],
            "message": ["db error", "fail to connect", "Error!"],  # case-sensitive
        }
    )
    traces = pd.DataFrame(
        {
            "serviceName": ["cart", "cart", "cart", "ad"],
            "methodName": ["Get", "Get", "Get", None],
            "operationName": ["x", "x", "x", "Late"],
            "startTime": [1 * US, 2 * US, 11 * US, 12 * US],
            "duration": [1000, 1000, 9000, 1000],
        }
    )
    out = pd_mod.pdiagnose({"metric": metric, "logs": logs, "traces": traces}, 10)
    # cart: metric 3 x 5 = 15; log 1 x 5 = 5; span: normal Get mean 1 ms sd 0,
    #   anomalous 9 ms >= 1 -> 1 x 5 = 5; total 25.
    # ad: 20 metric points x 5; the "Late" span has no normal reference.
    # redis: logs only, "fail..." matches, "Error!" does not -> 5.
    assert out["ranks"] == ["ad", "cart", "redis"]


def test_wrapper_metric_preparation(adapters: tuple[Any, Any]) -> None:
    _, rm = adapters
    df = pd.DataFrame(
        {
            "time": list(range(200, 210)),
            "time.1": list(range(10)),
            "a_latency-50": [1] * 10,
            "a_latency-90": [float("inf")] + [2] * 9,
            "b_cpu": [None, 1] + [3] * 8,
        }
    )
    assert len(rm.prepare_metrics(df, 205, 0)) == 0  # length 0: no rows kept
    out = rm.prepare_metrics(df, 205, 1)  # 30 rows either side: all 10 kept
    assert list(out.columns) == ["time", "a_latency", "b_cpu"]
    assert out["a_latency"].iloc[0] == 0  # inf -> NaN -> zero fill
    assert out["b_cpu"].iloc[0] == 0 and out["b_cpu"].iloc[1] == 1
    assert rm.METHODS[3] == "tracerca"
    rm.seed_everything(7)


def test_wrapper_runs_pdiagnose_end_to_end(
    tmp_path: Path, adapters: tuple[Any, Any]
) -> None:
    _, rm = adapters
    inp, out = tmp_path / "in", tmp_path / "out"
    export_window(window_of(capture(tmp_path, "inc-1")), tmp_path, inp)
    out.mkdir()
    job = {
        "method": "pdiagnose",
        "seed": 3,
        "anomaly_time": START + 50,
        "dataset": "re2-ob",
    }
    (inp / "job.json").write_text(json.dumps(job))
    assert rm.main(["x", str(inp), str(out)]) == 0
    result = json.loads((out / "result.json").read_text())
    assert set(result["ranks"]) == {"ad", "cart"} and result["cpu_ms"] >= 0
    job["method"] = "baro"  # RCAEval is not installed on the host: a method error
    (inp / "job.json").write_text(json.dumps(job))
    rm.main(["x", str(inp), str(out)])
    error = json.loads((out / "result.json").read_text())["error"]
    assert error.startswith("ModuleNotFoundError")


# ── Family B sensitivity rows and the CHASE anchor (B-b, B-e, B-f, B-k) ──────


def test_family_b_sensitivity_rows() -> None:
    from helios.analysis.run import CHASE_HR_AT_3, family_b_sensitivity

    cases = [f"c{i}" for i in range(6)]
    apps = dict.fromkeys(cases, "OB")
    groups = {c: c for c in cases}

    def row(hit: int, cpr: float, human: float) -> dict[str, Any]:
        return {
            "hr_at_3": hit,
            "avg_at_5": hit,
            "log_ttcd": math.log(cpr if hit else 1800 - cpr),
            "log_cpr": math.log(cpr),
            "cpr_total": cpr,
            "cpr_human": human,
            "h_fact": None,
            "h_struct": 0,
            "ttt_ms": 1,
        }

    trigger = BASELINES[0] + TRIGGER_SUFFIX
    table: dict[str, dict[str, dict[str, Any]]] = {
        "HELIOS-Full": {c: row(1, 12 + i, 10) for i, c in enumerate(cases)},
        BASELINES[0]: {c: row(0, 20 + i * i, 10) for i, c in enumerate(cases[:5])},
        trigger: {c: row(0, 21 + i * i, 10) for i, c in enumerate(cases)},
    }
    scheduled = dict.fromkeys(table, cases)
    out = family_b_sensitivity(
        table,
        apps,
        groups,
        scheduled,
        a_h7_mode="intersection_union",
        holm="data_order",
        confirmatory=False,
        covariates=None,
    )
    assert out["chase_anchor"]["hr_at_3"] == CHASE_HR_AT_3
    assert out["chase_anchor"]["baselines_hr_at_3"] == {BASELINES[0]: 0}
    trig = {r["id"]: r for r in out["trigger_time"]}
    assert trig["B-H1"]["n_pairs"] == 6  # the trigger run covers every case
    (b_h7,) = out["no_human_time"]
    assert b_h7["id"] == "B-H7"
    misses = out["failures_as_misses"]
    assert misses["filled"] == 1
    b_h1 = next(r for r in misses["hypotheses"] if r["id"] == "B-H1")
    assert b_h1["n_pairs"] == 6


# ── DockerRunner outcome classes (B-e, B-f), with subprocess faked ───────────


def test_docker_runner_outcome_classes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from helios.baselines.container import IMAGES, DockerRunner

    calls: list[list[str]] = []
    mode = {"run": "ok", "inspect": IMAGES["default"][1]}

    def fake_run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[1:3] == ["image", "inspect"]:
            if mode["inspect"] == "missing":
                return subprocess.CompletedProcess(cmd, 1, "", "no such image")
            return subprocess.CompletedProcess(cmd, 0, mode["inspect"] + "\n", "")
        if cmd[1] == "kill":
            return subprocess.CompletedProcess(cmd, 0, "", "")
        out_dir = Path(cmd[cmd.index("-v", cmd.index("-v") + 1) + 1].split(":")[0])
        m = mode["run"]
        if m == "timeout":
            raise subprocess.TimeoutExpired(cmd, 1)
        if m == "oom":
            return subprocess.CompletedProcess(cmd, 137, "", "")
        if m == "docker":
            return subprocess.CompletedProcess(cmd, 125, "", "daemon down")
        if m == "noresult":
            return subprocess.CompletedProcess(cmd, 1, "", "Traceback")
        wall = 2_000_000 if m == "late" else 5
        (out_dir / "result.json").write_text(
            json.dumps({"ranks": ["a_cpu"], "wall_ms": wall, "cpu_ms": 4})
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = DockerRunner()
    assert runner.check_image("default") == IMAGES["default"][1]
    mode["inspect"] = "sha256:other"
    with pytest.raises(BaselineConfigError, match="pinned"):
        runner.check_image("default")
    mode["inspect"] = "missing"
    with pytest.raises(BaselineConfigError, match="not available"):
        runner.check_image("rcd")
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    out.mkdir()
    limits = Limits(cpus=2, memory="1g", timeout_s=60)
    assert runner.run("default", inp, out, "n1", limits)["ranks"] == ["a_cpu"]
    cmd = calls[-1]
    assert cmd[cmd.index("--network") + 1] == "none"
    assert (
        cmd[cmd.index("--cpus") + 1] == "2" and cmd[cmd.index("--memory") + 1] == "1g"
    )
    assert f"{inp}:/in:ro" in cmd
    for m, exc in (
        ("oom", MemoryError),
        ("docker", ConnectionError),
        ("noresult", ConnectionError),
        ("timeout", BaselineTimeoutError),
        ("late", BaselineTimeoutError),
    ):
        (out / "result.json").unlink(missing_ok=True)
        mode["run"] = m
        with pytest.raises(exc):
            runner.run("default", inp, out, "n2", limits)
    assert calls[-2][1] == "kill"  # the timed-out container was killed
