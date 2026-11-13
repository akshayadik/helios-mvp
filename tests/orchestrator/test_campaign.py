"""S4.10 campaign: outcomes, retries, stop, resume (O-c, O-i) with a stub executor."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from helios.orchestrator.campaign import MAX_RETRIES, Campaign, read_log
from helios.orchestrator.runner import RunOutcome
from helios.orchestrator.schedule import Phase, build_schedule
from helios.pipelines.l_pipe.ollama_client import OllamaConnectionError
from helios.store.result_store import ResultStore
from helios.telemetry.trigger import ProvisionalParametersError
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.variants import EXPLORATORY_VARIANTS

if TYPE_CHECKING:
    from pathlib import Path

CASES = [f"{i:032x}" for i in range(4)]
APPS = dict.fromkeys(CASES, "OB")
ALL_EXPLORATORY = dict.fromkeys(EXPLORATORY_VARIANTS, "x")


class Crash(BaseException):
    """Stands in for the process dying mid-run (never caught)."""


class Stub:
    """Executor double. ``plan`` maps a case to what successive calls do:
    an exception to raise, or an outcome string to return."""

    def __init__(self, name: str, plan: dict[str, list[Any]] | None = None) -> None:
        self.name = name
        self.plan = {k: list(v) for k, v in (plan or {}).items()}
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self.discarded: list[str] = []
        self.prepared = 0

    @property
    def config_hash(self) -> str:
        return f"hash-{self.name}"

    def prepare(self) -> None:
        self.prepared += 1

    def run_incident(
        self, incident_id: str, run_id: str, context: Any = None
    ) -> RunOutcome:
        self.calls.append((incident_id, run_id, dict(context or {})))
        steps = self.plan.get(incident_id)
        step = steps.pop(0) if steps else "passed"
        if isinstance(step, BaseException):
            raise step
        gate = None if step == "passed" else "capture_seal_invalid"
        return RunOutcome(step, gate, {})

    def discard_run(self, run_id: str) -> int:
        self.discarded.append(run_id)
        return 1


class Ledger:
    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    def append(self, fields: dict[str, str]) -> None:
        self.entries.append(fields)


def _setup(
    tmp_path: Path, plans: dict[str, dict[str, list[Any]]] | None = None
) -> tuple[Campaign, dict[str, Stub], Ledger]:
    schedule = build_schedule("build", CASES, APPS, refused=ALL_EXPLORATORY)
    systems = {s.system for s in schedule.specs}
    stubs = {s: Stub(s, (plans or {}).get(s)) for s in systems}
    ledger = Ledger()
    camp = Campaign(tmp_path / "c", schedule, stubs, exclusion_ledger=ledger)
    return camp, stubs, ledger


def _final(camp: Campaign) -> dict[str, dict[str, Any]]:
    return camp.state().final


def test_all_pass_and_run_ids_follow_the_schedule(tmp_path: Path) -> None:
    camp, stubs, ledger = _setup(tmp_path)
    done = camp.run([Phase.CONFIRMATORY])
    assert done == {"passed": 32}
    assert ledger.entries == []
    full = stubs["HELIOS-Full"]
    assert full.prepared == 1
    _, _, ctx = full.calls[0]
    assert ctx["phase"] == "confirmatory" and ctx["attempt"] == "0"
    assert ctx["schedule_digest"] == camp._digest
    assert int(ctx["seed"]) >= 10_000_000
    # Case-major: the first eight calls are one case, noRouter first.
    log = [r for r in read_log(camp.log_path) if r["event"] == "started"]
    assert {r["key"].split("/")[1] for r in log[:8]} == {CASES[0]}
    assert log[0]["key"].endswith("HELIOS-noRouter")
    # A second run is a no-op: everything is final.
    assert camp.run([Phase.CONFIRMATORY]) == {}


def test_gate_exclusion_is_final_without_campaign_ledger_entry(tmp_path: Path) -> None:
    camp, _, ledger = _setup(tmp_path, {"HELIOS-D": {CASES[1]: ["excluded"]}})
    assert camp.run([Phase.CONFIRMATORY]) == {"passed": 31, "excluded": 1}
    # The executor's own gate writes its entry; the campaign adds none.
    assert ledger.entries == []
    rec = _final(camp)[f"confirmatory/{CASES[1]}/HELIOS-D"]
    assert rec["gate_check"] == "capture_seal_invalid"


def test_infrastructure_error_is_retried_then_passes(tmp_path: Path) -> None:
    plan = {"HELIOS-Full": {CASES[0]: [OllamaConnectionError("down"), "passed"]}}
    camp, stubs, ledger = _setup(tmp_path, plan)
    camp.run([Phase.CONFIRMATORY])
    full = stubs["HELIOS-Full"]
    first, second = (c for c in full.calls if c[0] == CASES[0])
    assert first[1] != second[1]  # a new attempt, a new run id
    assert second[2]["attempt"] == "1"
    assert full.discarded == [first[1]]
    assert _final(camp)[f"confirmatory/{CASES[0]}/HELIOS-Full"]["event"] == "passed"
    assert ledger.entries == []


def test_retries_exhausted_is_an_exclusion(tmp_path: Path) -> None:
    errors = [TimeoutError("slow") for _ in range(MAX_RETRIES + 1)]
    camp, stubs, ledger = _setup(tmp_path, {"HELIOS-G": {CASES[2]: errors}})
    camp.run([Phase.CONFIRMATORY])
    assert len([c for c in stubs["HELIOS-G"].calls if c[0] == CASES[2]]) == 3
    (entry,) = ledger.entries
    assert entry["gate_check"] == "infrastructure_retries_exhausted"
    assert entry["variant_config_hash"] == "hash-HELIOS-G"
    assert entry["attempt"] == str(MAX_RETRIES)
    assert entry["covariates"] == "{}"
    log = read_log(camp.log_path)
    assert sum(r["event"] == "retry" for r in log) == MAX_RETRIES


def test_run_error_is_excluded_and_the_campaign_continues(tmp_path: Path) -> None:
    camp, _, ledger = _setup(
        tmp_path, {"HELIOS-noLLM": {CASES[0]: [ValueError("bad graph")]}}
    )
    assert camp.run([Phase.CONFIRMATORY]) == {"passed": 31, "excluded": 1}
    (entry,) = ledger.entries
    assert entry["gate_check"] == "run_error"
    assert entry["reason"].startswith("ValueError: bad graph (traceback ")


def test_configuration_refusal_stops_the_campaign(tmp_path: Path) -> None:
    plan = {"HELIOS-Full": {CASES[0]: [ProvisionalParametersError("freeze")]}}
    camp, _, ledger = _setup(tmp_path, plan)
    with pytest.raises(ProvisionalParametersError):
        camp.run([Phase.CONFIRMATORY])
    assert ledger.entries == []
    log = read_log(camp.log_path)
    assert log[-1]["event"] == "stopped"
    # Resume: the stopped spec runs again (its rows discarded first).
    assert camp.run([Phase.CONFIRMATORY])["passed"] >= 1


def test_crash_and_resume_discards_the_unfinished_run(tmp_path: Path) -> None:
    camp, stubs, _ = _setup(tmp_path, {"HELIOS-D": {CASES[0]: [Crash()]}})
    with pytest.raises(Crash):
        camp.run([Phase.CONFIRMATORY])
    stale = stubs["HELIOS-D"].calls[-1][1]
    assert camp.state().open_run == {f"confirmatory/{CASES[0]}/HELIOS-D": stale}
    assert camp.run([Phase.CONFIRMATORY])["passed"] == 32 - 4  # 4 done pre-crash
    assert stubs["HELIOS-D"].discarded == [stale]
    again = [c for c in stubs["HELIOS-D"].calls if c[0] == CASES[0]][-1]
    assert again[2]["attempt"] == "1"
    assert len(_final(camp)) == 32


def test_limit_missing_executor_and_schedule_change(tmp_path: Path) -> None:
    camp, stubs, ledger = _setup(tmp_path)
    assert camp.run([Phase.CONFIRMATORY], limit=3) == {"passed": 3}
    with pytest.raises(ValueError, match="no executor"):
        Campaign(
            tmp_path / "c",
            camp._schedule,
            {},
            exclusion_ledger=ledger,
        ).run([Phase.BASELINE])
    other = build_schedule("build", CASES[:2], APPS, refused=ALL_EXPLORATORY)
    with pytest.raises(ValueError, match="start a new campaign"):
        Campaign(tmp_path / "c", other, stubs, exclusion_ledger=ledger)
    body = json.loads((tmp_path / "c" / "schedule.json").read_text())
    assert body["digest"] == camp._digest


def test_store_transaction_rolls_back_and_delete_run(tmp_path: Path) -> None:
    store = ResultStore(tmp_path / "r.duckdb")
    with pytest.raises(RuntimeError), store.transaction():
        store.insert_graph_timing("run-a", 1, 2)
        raise RuntimeError("mid-run")
    assert store.fetch_timings("run-a") == []
    with store.transaction():
        store.insert_graph_timing("run-b", 1, 2)
    assert len(store.fetch_timings("run-b")) == 1
    assert store.delete_run("run-b") == 1
    assert store.fetch_timings("run-b") == []
    store.close()


def test_full_schedule_dry_run_on_fixtures(tmp_path: Path) -> None:
    """O-j (1): the full-size schedule (240 cases, 2 systems) through stub
    executors with injected faults, a crash and a resume, then the cells."""
    order = [f"{i:032x}" for i in range(240)]
    apps = {c: ("OB" if i % 2 == 0 else "TT") for i, c in enumerate(order)}
    refused = dict.fromkeys(
        ("HELIOS-noCogni", "HELIOS-HIS3", "HELIOS-noFGSV", "HELIOS-noIOL"), "x"
    )
    schedule = build_schedule("pool", order, apps, refused=refused)
    tt = [c for c in order if apps[c] == "TT"]
    plans: dict[str, dict[str, list[Any]]] = {
        # 30 of 120 TT cases excluded for noStructural -> its TT cells fail.
        "HELIOS-noStructural": {c: ["excluded"] for c in tt[:30]},
        "HELIOS-Full": {order[5]: [OllamaConnectionError("blip"), "passed"]},
        "HELIOS-G": {order[7]: [ValueError("bad")]},
        "HELIOS-D": {order[100]: [Crash()]},
    }
    stubs = {s: Stub(s, plans.get(s)) for s in {x.system for x in schedule.specs}}
    ledger = Ledger()
    camp = Campaign(tmp_path / "c", schedule, stubs, exclusion_ledger=ledger)
    with pytest.raises(Crash):
        camp.run()
    camp = Campaign(tmp_path / "c", schedule, stubs, exclusion_ledger=ledger)
    camp.run()
    final = camp.state().final
    assert len(final) == len(schedule.specs) == 1920 + 1200 + 720 + 192
    outcomes = [r["event"] for r in final.values()]
    assert outcomes.count("excluded") == 30 + 1
    assert [e["gate_check"] for e in ledger.entries] == ["run_error"]
    assert stubs["HELIOS-D"].discarded  # the crashed run was discarded
    # Cells from the outcomes: a run that passed has every metric.
    from helios.evaluation.cells import CELL_METRICS, cell_key, cell_table
    from helios.orchestrator.schedule import scheduled_by_system, system_name

    table: dict[str, dict[str, dict[str, Any]]] = {}
    for key, rec in final.items():
        phase, case, system = key.split("/")
        if phase != Phase.RERUN and rec["event"] == "passed":
            table.setdefault(system_name(system), {})[case] = dict.fromkeys(
                CELL_METRICS, 1
            )
    cells = cell_table(table, apps, scheduled_by_system(schedule.body()))
    assert not cells[cell_key("HELIOS-noStructural", "TT", "hr_at_3")].passes
    assert cells[cell_key("HELIOS-noStructural", "OB", "hr_at_3")].passes
    assert cells[cell_key("HELIOS-G", "TT", "hr_at_3")].passes  # 119 of 120
