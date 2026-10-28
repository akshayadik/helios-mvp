"""S1.2 OTel Demo build campaign: schedule, flags, signed labels, resume, slicing."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pyarrow as pa
import pytest

import bin.capture_campaign as cli
from helios.adapters.otel_campaign import (
    CAPTURE_RETRY_WAIT_S,
    CORPUS_V2,
    FAULTS,
    INGEST_LAG_S,
    POST_S,
    PRE_S,
    PRE_S_MAX,
    PRE_S_MIN,
    PRE_S_STEP,
    RECOVERY_S,
    Campaign,
    FlagdFile,
    GroundTruthFile,
    PlannedCase,
    opaque_id,
    plan,
    pre_s_for,
)
from helios.evaluation.scoring import Corpus, load_ground_truth
from helios.telemetry.otel_demo_capture import (
    SlicedFetcher,
    StreamFetcher,
    build_campaign_capture,
)
from helios.vcl import VCLFlag, get_variant  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"k" * 32
T0 = datetime(2026, 10, 27, 1, 0, tzinfo=UTC)


# ── schedule ────────────────────────────────────────────────────────────────


def test_plan_is_rep_major_balanced_and_opaque() -> None:
    cases = plan(7)
    assert len(cases) == 63
    assert [c.fault.flag for c in cases[:9]] == [f.flag for f in FAULTS]
    assert Counter(c.fault.flag for c in cases) == {f.flag: 7 for f in FAULTS}
    payment = [c.variant for c in cases if c.fault.flag == "paymentFailure"]
    assert payment[:4] == ["90%", "75%", "50%", "90%"]
    ids = [c.incident_id for c in cases]
    assert len(set(ids)) == 63
    assert all(len(i) == 32 and int(i, 16) >= 0 for i in ids)
    for c in cases:  # the ID reveals nothing about the fault
        assert c.fault.flag.lower() not in c.incident_id
        assert c.incident_id == opaque_id(c.case)
    assert plan(7) == cases  # deterministic
    assert {c.fault.root_cause_service for c in cases} == {
        "ad",
        "cart",
        "checkout",
        "email",
        "payment",
        "product-catalog",
        "recommendation",
    }
    with pytest.raises(ValueError, match="reps"):
        plan(0)


# ── flagd file ──────────────────────────────────────────────────────────────


def _flagd(tmp_path: Path) -> Path:
    doc = {
        "flags": {
            "adHighCpu": {
                "variants": {"on": True, "off": False},
                "defaultVariant": "off",
            },
            "paymentFailure": {
                "variants": {"90%": 0.9, "50%": 0.4, "off": 0},
                "defaultVariant": "off",
            },
            "noOffFlag": {"variants": {"a": 1, "b": 2}, "defaultVariant": "a"},
        }
    }
    path = tmp_path / "demo.flagd.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def test_flagd_file_is_edited_in_place(tmp_path: Path) -> None:
    path = _flagd(tmp_path)
    inode = path.stat().st_ino
    flagd = FlagdFile(path)
    flagd.set("paymentFailure", "90%")
    assert flagd.state()["paymentFailure"] == "90%"
    flagd.set("adHighCpu", "on")
    flagd.all_off()
    assert flagd.state() == {
        "adHighCpu": "off",
        "paymentFailure": "off",
        "noOffFlag": "a",
    }
    assert path.stat().st_ino == inode  # the bind mount keeps seeing the file
    with pytest.raises(KeyError):
        flagd.set("nope", "on")
    with pytest.raises(ValueError, match="no variant"):
        flagd.set("adHighCpu", "maybe")


# ── signed ground truth ─────────────────────────────────────────────────────


def test_ground_truth_is_signed_append_only_and_scorable(tmp_path: Path) -> None:
    path = tmp_path / "data" / "otel" / "ground_truth_build.json"
    gt = GroundTruthFile(path, KEY, demo_commit="b74a7bc")
    assert gt.cases() == {}
    gt.add("a" * 32, {"root_cause_service": "cart", "case": "x"})
    gt.add("b" * 32, {"root_cause_service": "ad", "case": "y"})
    assert set(gt.cases()) == {"a" * 32, "b" * 32}
    with pytest.raises(ValueError, match="append-only"):
        gt.add("a" * 32, {"root_cause_service": "cart"})
    loaded = load_ground_truth(Corpus.OTEL_BUILD, root=tmp_path, key=KEY)
    assert loaded.labels == {"a" * 32: "cart", "b" * 32: "ad"}
    assert not loaded.stem  # node names, matched exactly
    path.write_text(path.read_text().replace('"cart"', '"email"'), encoding="utf-8")
    with pytest.raises(ValueError, match="does not verify"):
        gt.cases()


# ── campaign runner ─────────────────────────────────────────────────────────


class _Clock:
    def __init__(self) -> None:
        self.now = T0
        self.slept: list[float] = []

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.now += timedelta(seconds=s)

    def __call__(self) -> datetime:
        return self.now


def _campaign(
    tmp_path: Path, cases: list[PlannedCase], **kw: object
) -> tuple[Campaign, _Clock, list[str]]:
    clock = _Clock()
    events: list[str] = []
    flagd_path = tmp_path / "flagd.json"
    flagd_path.write_text(
        json.dumps(
            {
                "flags": {
                    f.flag: {
                        "variants": {**{v: v for v in f.variants}, "off": "off"},
                        "defaultVariant": "off",
                    }
                    for f in FAULTS
                }
            }
        )
    )
    flagd = FlagdFile(flagd_path)

    def capture(case: PlannedCase, start: datetime, end: datetime) -> None:
        events.append(
            f"capture {case.fault.flag} {start.isoformat()} {end.isoformat()}"
        )
        (tmp_path / "build" / case.incident_id).mkdir(parents=True)

    defaults: dict[str, object] = {
        "cases": cases,
        "captures_dir": tmp_path / "build",
        "flagd": flagd,
        "ground_truth": GroundTruthFile(tmp_path / "gt.json", KEY, demo_commit="c"),
        "capture": capture,
        "confirm_flag": lambda flag, variant: flagd.state()[flag] == variant,
        "restart": lambda service: events.append(f"restart {service}"),
        "sleep": clock.sleep,
        "clock": clock,
        "log": events.append,
    }
    defaults.update(kw)
    return Campaign(**defaults), clock, events  # type: ignore[arg-type]


def test_a_case_is_normal_then_fault_then_captured(tmp_path: Path) -> None:
    cases = plan(1)
    campaign, clock, events = _campaign(tmp_path, cases)
    assert campaign.run(limit=1) == 1
    assert clock.slept == [RECOVERY_S + PRE_S, POST_S, INGEST_LAG_S]
    inject = T0 + timedelta(seconds=RECOVERY_S + PRE_S)
    start, end = inject - timedelta(seconds=PRE_S), inject + timedelta(seconds=POST_S)
    assert f"capture adHighCpu {start.isoformat()} {end.isoformat()}" in events
    label = campaign.ground_truth.cases()[cases[0].incident_id]
    assert label["root_cause_service"] == "ad"
    assert label["inject_time"] == inject.isoformat()
    assert (label["window_start"], label["window_end"]) == (
        start.isoformat(),
        end.isoformat(),
    )
    assert set(campaign.flagd.state().values()) == {"off"}  # left clean


def test_campaign_resumes_redoes_partial_and_restarts_leaky_services(
    tmp_path: Path,
) -> None:
    cases = plan(1)
    campaign, _, events = _campaign(tmp_path, cases)
    campaign.run(limit=2)
    partial = tmp_path / "build" / cases[2].incident_id
    partial.mkdir(parents=True)
    (partial / "p1_metrics.parquet").write_text("half-written")
    campaign.run()  # resumes with case 3, records the partial case again
    assert len(campaign.ground_truth.cases()) == 9
    assert not (partial / "p1_metrics.parquet").exists()
    assert events.count("restart email") == 1
    assert sum(e.startswith("capture") for e in events) == 9
    assert campaign.pending() == []
    assert campaign.run() == 0


def test_flag_that_never_takes_effect_stops_the_campaign_clean(tmp_path: Path) -> None:
    campaign, _clock, _ = _campaign(
        tmp_path, plan(1), confirm_flag=lambda flag, variant: False
    )
    with pytest.raises(RuntimeError, match="did not serve"):
        campaign.run()
    assert set(campaign.flagd.state().values()) == {"off"}
    assert campaign.ground_truth.cases() == {}


# ── sliced fetching ─────────────────────────────────────────────────────────


class _MinuteFetcher(StreamFetcher):
    """One row per minute of the requested range, plus the row at its end bound."""

    def __init__(self) -> None:
        self.calls: list[tuple[datetime, datetime]] = []

    @property
    def stream_name(self) -> str:
        return "p2_traces"

    def fetch(self, start: datetime, end: datetime) -> pa.Table:
        self.calls.append((start, end))
        minutes = [
            start + timedelta(minutes=i)
            for i in range(int((end - start).total_seconds() // 60) + 1)
        ]
        return pa.table({"t": [m.isoformat() for m in minutes]})


def test_sliced_fetcher_covers_the_window_once(tmp_path: Path) -> None:
    inner = _MinuteFetcher()
    table = SlicedFetcher(inner, 60).fetch(T0, T0 + timedelta(minutes=10))
    assert len(inner.calls) == 10
    assert table.column("t").to_pylist() == [
        (T0 + timedelta(minutes=i)).isoformat() for i in range(11)
    ]  # boundary rows kept once
    assert SlicedFetcher(inner, 60).stream_name == "p2_traces"
    assert SlicedFetcher(inner, 60).fetch(T0, T0).num_rows == 1
    with pytest.raises(ValueError, match="slice_s"):
        SlicedFetcher(inner, 0)


def test_campaign_capture_wiring(tmp_path: Path) -> None:
    cap = build_campaign_capture(
        "x" * 32,
        get_variant("HELIOS-Full"),
        output_dir=tmp_path,
        prometheus_url="http://p",
        jaeger_url="http://j",
        opensearch_url="http://o",
    )
    kinds = [type(f).__name__ for f in cap._fetchers]
    assert kinds == ["PrometheusMetricsFetcher", "SlicedFetcher", "SlicedFetcher"]
    from helios.telemetry.otel_demo_capture import campaign_metric_queries

    # The campaign records the container CPU and memory queries, not the May list.
    assert cap._fetchers[0]._queries == campaign_metric_queries()  # type: ignore[attr-defined]
    assert cap._config.output_dir == tmp_path


# ── CLI (offline commands) ──────────────────────────────────────────────────


def test_cli_status_verify_finalize_print_counts_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli, "CAPTURES_DIR", tmp_path / "build")
    monkeypatch.setattr(cli, "_demo_commit", lambda: "b74a7bc")
    monkeypatch.setattr(cli, "load_key", lambda: KEY)
    (tmp_path / "data" / "otel").mkdir(parents=True)
    gt = GroundTruthFile(tmp_path / cli.GROUND_TRUTH, KEY, demo_commit="b74a7bc")
    first = plan(1)[0]
    gt.add(first.incident_id, {"root_cause_service": "ad", "case": first.case})

    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "1/63 cases captured and labelled" in out
    assert first.incident_id not in out

    assert cli.main(["verify"]) == 1  # labelled but no capture on disk
    assert "0 intact" in capsys.readouterr().out

    assert cli.main(["finalize"]) == 0
    manifest = json.loads((tmp_path / cli.CORPUS_MANIFEST).read_text())
    assert manifest["case_order"] == [first.incident_id]
    assert manifest["evaluation_phase"] == "exploratory"
    assert "root_cause_service" not in json.dumps(manifest)


def test_campaign_metrics_add_container_cpu_and_memory() -> None:
    from helios.telemetry.otel_demo_capture import (
        DEMO_CONTAINERS,
        PrometheusMetricsFetcher,
        campaign_metric_queries,
    )

    queries = campaign_metric_queries()
    assert queries[:2] == (
        "http_server_duration_milliseconds_bucket",
        "rpc_server_duration_milliseconds_bucket",
    )
    for name in (
        "container_cpu_utilization_ratio",
        "container_memory_usage_total_bytes",
    ):
        q = next(q for q in queries if name in q)
        assert q.startswith(f'label_replace({name}{{container_name=~"')
        assert '"service_name", "$1", "container_name", "(.*)")' in q
    assert {"ad", "email", "valkey-cart"} <= set(DEMO_CONTAINERS)
    assert not any(c.startswith("tessera") for c in DEMO_CONTAINERS)
    fetcher = PrometheusMetricsFetcher("http://p", queries)
    assert fetcher._queries == queries
    assert (
        PrometheusMetricsFetcher("http://p")._queries[0] == "up"
    )  # May list unchanged


# ── v2: varied normal period (S2.1 recapture, 2026-10-27) ───────────────────


def test_v1_plan_is_unchanged() -> None:
    cases = plan(7)
    assert {c.pre_s for c in cases} == {PRE_S}
    assert all(c.case.startswith("otel_build/") for c in cases)


def test_v2_plan_varies_the_normal_period_deterministically() -> None:
    v2 = plan(7, corpus=CORPUS_V2)
    assert plan(7, corpus=CORPUS_V2) == v2
    assert all(c.case.startswith(f"{CORPUS_V2}/") for c in v2)
    assert {c.incident_id for c in v2}.isdisjoint({c.incident_id for c in plan(7)})
    pre = [c.pre_s for c in v2]
    assert min(pre) >= PRE_S_MIN and max(pre) <= PRE_S_MAX
    assert all((p - PRE_S_MIN) % PRE_S_STEP == 0 for p in pre)
    assert len(set(pre)) >= 10  # position no longer reveals the onset
    assert all(c.pre_s == pre_s_for(c.incident_id) for c in v2)


def test_v2_case_uses_its_own_normal_period(tmp_path: Path) -> None:
    cases = plan(1, corpus=CORPUS_V2)
    campaign, clock, events = _campaign(
        tmp_path,
        cases,
        ground_truth=GroundTruthFile(
            tmp_path / "gt.json", KEY, demo_commit="c", corpus=CORPUS_V2
        ),
    )
    campaign.run(limit=1)
    pre = cases[0].pre_s
    assert clock.slept == [RECOVERY_S + pre, POST_S, INGEST_LAG_S]
    inject = T0 + timedelta(seconds=RECOVERY_S + pre)
    label = campaign.ground_truth.cases()[cases[0].incident_id]
    assert label["window_start"] == (inject - timedelta(seconds=pre)).isoformat()
    assert json.loads((tmp_path / "gt.json").read_text())["corpus"] == CORPUS_V2
    assert f"[campaign] case 1/9: normal period ({pre}s)" in events


def test_cli_v2_corpus_has_its_own_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli, "_demo_commit", lambda: "b74a7bc")
    monkeypatch.setattr(cli, "load_key", lambda: KEY)
    captures, truth, manifest = cli._paths(CORPUS_V2)
    assert captures.name == "build_v2"
    assert truth.name == "ground_truth_build_v2.json"
    (tmp_path / truth).parent.mkdir(parents=True)
    first = plan(1, corpus=CORPUS_V2)[0]
    GroundTruthFile(tmp_path / truth, KEY, demo_commit="b74a7bc", corpus=CORPUS_V2).add(
        first.incident_id, {"root_cause_service": "ad", "case": first.case}
    )
    assert cli.main(["status", "--corpus", CORPUS_V2]) == 0
    out = capsys.readouterr().out
    assert "1/63 cases captured and labelled" in out
    assert cli.main(["finalize", "--corpus", CORPUS_V2]) == 0
    written = json.loads((tmp_path / manifest).read_text())
    assert written["corpus"] == CORPUS_V2
    assert written["protocol"]["pre_s"] == {"min": 480, "max": 900, "step": 15}
    assert cli.main(["status"]) == 0  # v1 still the default
    assert "0/63" in capsys.readouterr().out


# ── v3: span metrics, 25-user load, pilot (S2-M7-ENG10, 2026-10-28) ─────────


def test_v3_and_pilot_plans_vary_the_normal_period_and_stay_disjoint() -> None:
    from helios.adapters.otel_campaign import CORPUS_PILOT_V3, CORPUS_V3

    v3 = plan(7, corpus=CORPUS_V3)
    assert len(v3) == 63
    assert all(c.pre_s == pre_s_for(c.incident_id) for c in v3)
    pilot = plan(1, corpus=CORPUS_PILOT_V3)
    ids = [{c.incident_id for c in p} for p in (v3, pilot, plan(7, corpus=CORPUS_V2))]
    assert ids[0].isdisjoint(ids[1]) and ids[0].isdisjoint(ids[2])


def test_plan_can_be_limited_to_named_faults() -> None:
    from helios.adapters.otel_campaign import CORPUS_PILOT_V3

    hard = ("paymentFailure", "productCatalogFailure", "recommendationCacheFailure")
    cases = plan(1, corpus=CORPUS_PILOT_V3, faults=hard)
    assert [c.fault.flag for c in cases] == list(hard)
    with pytest.raises(ValueError, match="unknown fault"):
        plan(1, corpus=CORPUS_PILOT_V3, faults=("noSuchFlag",))


def test_v3_corpora_run_at_twenty_five_users() -> None:
    from helios.adapters.otel_campaign import (
        CORPUS,
        CORPUS_PILOT_V3,
        CORPUS_V3,
        load_users_for,
    )

    assert load_users_for(CORPUS_V3) == 25
    assert load_users_for(CORPUS_PILOT_V3) == 25
    assert load_users_for(CORPUS) is None  # v1/v2 ran at the demo's 5, unenforced
    assert load_users_for(CORPUS_V2) is None


def test_campaign_checks_load_before_every_case_and_records_it(
    tmp_path: Path,
) -> None:
    checks: list[str] = []
    cases = plan(1)[:2]
    campaign, _, _ = _campaign(
        tmp_path, cases, check_load=lambda: checks.append("ok"), load_users=25
    )
    campaign.run()
    assert checks == ["ok", "ok"]
    labels = campaign.ground_truth.cases()
    assert {v["load_users"] for v in labels.values()} == {25}


def test_campaign_stops_when_the_load_is_wrong(tmp_path: Path) -> None:
    def wrong() -> None:
        raise RuntimeError("load generator runs 5 users, expected 25")

    campaign, _, events = _campaign(tmp_path, plan(1), check_load=wrong)
    with pytest.raises(RuntimeError, match="expected 25"):
        campaign.run()
    assert campaign.ground_truth.cases() == {}
    assert not any(e.startswith("capture") for e in events)


def test_v3_capture_records_span_metrics_not_histogram_buckets(
    tmp_path: Path,
) -> None:
    from helios.telemetry.otel_demo_capture import campaign_metric_queries

    queries = campaign_metric_queries(span_metrics=True)
    assert not any("_bucket" in q for q in queries)
    for name in (
        "span_calls_total",
        "span_error_calls_total",
        "span_mean_latency_milliseconds",
        "container_cpu_utilization_ratio",
        "container_memory_usage_total_bytes",
    ):
        assert any(name in q for q in queries), name
    error = next(q for q in queries if "span_error_calls_total" in q)
    assert 'status_code="STATUS_CODE_ERROR"' in error
    assert all(
        "SPAN_KIND_SERVER|SPAN_KIND_CONSUMER" in q for q in queries if "span_" in q
    )
    cap = build_campaign_capture(
        "x" * 32,
        get_variant("HELIOS-Full"),
        output_dir=tmp_path,
        prometheus_url="http://p",
        jaeger_url="http://j",
        opensearch_url="http://o",
        span_metrics=True,
    )
    assert cap._fetchers[0]._queries == queries  # type: ignore[attr-defined]
    assert campaign_metric_queries() != queries  # v1/v2 definition unchanged


def test_cli_v3_and_pilot_corpora_have_their_own_files() -> None:
    from helios.adapters.otel_campaign import CORPUS_PILOT_V3, CORPUS_V3

    captures, truth, manifest = cli._paths(CORPUS_V3)
    assert (captures.name, truth.name, manifest.name) == (
        "build_v3",
        "ground_truth_build_v3.json",
        "build_v3_manifest.json",
    )
    captures, truth, manifest = cli._paths(CORPUS_PILOT_V3)
    assert (captures.name, truth.name, manifest.name) == (
        "pilot_v3",
        "ground_truth_pilot_v3.json",
        "pilot_v3_manifest.json",
    )


def test_cli_sets_and_checks_the_locust_user_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, dict[str, str] | None]] = []
    state = {"user_count": 5}

    def fake(url: str, form: dict[str, str] | None = None) -> dict[str, object]:
        sent.append((url, form))
        if form is not None:
            state["user_count"] = int(form["user_count"])
            return {"success": True}
        return {"state": "running", "user_count": state["user_count"]}

    monkeypatch.setattr(cli, "_locust_call", fake)
    cli.set_load("http://lg", 25)
    assert sent[0] == ("http://lg/swarm", {"user_count": "25", "spawn_rate": "5"})
    cli.check_load("http://lg", 25)  # passes
    state["user_count"] = 5
    with pytest.raises(RuntimeError, match="5 users, expected 25"):
        cli.check_load("http://lg", 25)


def test_span_latency_rate_window_covers_two_collector_flushes() -> None:
    # The collector's span metrics arrive once a minute: a 1 min rate window
    # holds one sample and returns nothing (pilot v3, 2026-10-28).
    from helios.telemetry.otel_demo_capture import campaign_metric_queries

    latency = next(
        q
        for q in campaign_metric_queries(span_metrics=True)
        if "span_mean_latency" in q
    )
    assert latency.count("[2m]") == 2
    assert "[1m]" not in latency


def test_capture_retries_after_a_backend_drops_the_connection(tmp_path: Path) -> None:
    # 2026-10-28: OpenSearch restarted mid-query in case 10 of otel_build_v3;
    # the fault window was already stored, so the capture can be fetched again.
    cases = plan(1)
    calls: list[int] = []

    def flaky(case: PlannedCase, start: datetime, end: datetime) -> None:
        calls.append(1)
        (tmp_path / "build" / case.incident_id).mkdir(parents=True)
        if len(calls) == 1:
            raise ConnectionResetError("Remote end closed connection")

    campaign, clock, events = _campaign(tmp_path, cases, capture=flaky)
    assert campaign.run(limit=1) == 1
    assert len(calls) == 2
    assert CAPTURE_RETRY_WAIT_S in clock.slept
    assert any("retrying" in e for e in events)
    assert cases[0].incident_id in campaign.ground_truth.cases()


def test_capture_gives_up_after_its_retries(tmp_path: Path) -> None:
    def down(case: PlannedCase, start: datetime, end: datetime) -> None:
        raise ConnectionRefusedError("backend down")

    campaign, _, _ = _campaign(tmp_path, plan(1), capture=down)
    with pytest.raises(ConnectionRefusedError):
        campaign.run()
    assert campaign.ground_truth.cases() == {}
    assert set(campaign.flagd.state().values()) == {"off"}
