"""S5.1 system test checks (design s5_1_system_test_design.md S-c, S-d).

The per-variant dynamic check of S5.2 (design D-e): every runnable variant
runs the real pipelines on one OTel build case (stub model client), and every
run must carry the visible mark of each flag's state.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

import pytest

from bin import system_test_checks as st
from helios.vcl import (
    CONFIRMATORY_VARIANTS,
    EXPLORATORY_VARIANTS,
    VCLFlag,
    get_variant,
)
from helios.vcl.disjointness import NO_CONSUMER
from tests.test_runner_coe import _entries, _orch

if TYPE_CHECKING:
    from pathlib import Path

RUNNABLE = [
    *CONFIRMATORY_VARIANTS,
    *(
        name
        for name in EXPLORATORY_VARIANTS
        if name not in {"HELIOS-noCogni", "HELIOS-HIS3"}
    ),
]


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    """variant -> its one CoE entry on the staged OTel build case."""
    out: dict[str, dict[str, Any]] = {}
    for name in RUNNABLE:
        base = tmp_path_factory.mktemp(name)
        orch = _orch(base, name, coe_path=base / "coe.jsonl", frozen_router=True)
        orch.run(base / "captures")
        (entry,) = _entries(base / "coe.jsonl")
        out[name] = entry
    return out


def test_thirteen_variants_are_runnable() -> None:
    assert len(RUNNABLE) == 13
    no_consumer = {f.value for f in NO_CONSUMER}
    full = get_variant("HELIOS-Full")
    for name in set(EXPLORATORY_VARIANTS) - set(RUNNABLE):
        off = {
            f.value
            for f in VCLFlag.bool_flags()
            if getattr(get_variant(name), f.value) != getattr(full, f.value)
        }
        assert off <= no_consumer


@pytest.mark.parametrize("name", RUNNABLE)
def test_every_run_carries_the_marks_of_its_flags(
    runs: dict[str, dict[str, Any]], name: str
) -> None:
    assert st.run_marks(runs[name], get_variant(name)) == []


def test_record_only_variants_publish_fulls_decisions(
    runs: dict[str, dict[str, Any]],
) -> None:
    by_variant = {name: {"case": entry} for name, entry in runs.items()}
    unchanged = st.unchanged_verdicts(by_variant)
    assert set(unchanged) == set(st.RECORD_ONLY)
    assert all(u == {"cases": 1, "differ": []} for u in unchanged.values())
    tops = st.top1_differences(by_variant)
    assert set(tops) == set(RUNNABLE) - {"HELIOS-Full"}


def test_the_case_exercises_the_on_marks(runs: dict[str, dict[str, Any]]) -> None:
    corpus = st.exercised((get_variant(n), e) for n, e in runs.items())
    assert corpus["ueg_structural_features"]["result"] == "pass"
    assert corpus["l2c_llm_ranked"]["result"] == "pass"
    # Propagation evidence is recorded only where propagation changes a
    # score, so one case may show none; the corpus-level rule is checked on
    # the build campaigns (OTel v3 in S4.10: 125 of 291 runs).
    assert corpus["dpipe_propagation"]["possible"] > 0
    assert corpus["dpipe_propagation"]["result"] == "reported"


def test_parameter_hashes_equal_the_frozen_files(
    runs: dict[str, dict[str, Any]],
) -> None:
    assert st.parameter_problems(runs.values(), st.frozen_parameter_hashes()) == []


# ── planted faults ──────────────────────────────────────────────────────────


def test_a_wrong_mark_is_found(runs: dict[str, dict[str, Any]]) -> None:
    noiol = copy.deepcopy(runs["HELIOS-noIOL"])
    noiol["steps"].append({"id": "S", "measured": {}})
    assert st.run_marks(noiol, get_variant("HELIOS-noIOL")) == [
        "iol_self_telemetry OFF: step S present"
    ]
    full = copy.deepcopy(runs["HELIOS-Full"])
    full["steps"] = [s for s in full["steps"] if s["id"] != "N"]
    full["parameter_hashes"].pop("router")
    problems = st.run_marks(full, get_variant("HELIOS-Full"))
    assert "coe_narrative ON: no step N" in problems
    assert "cbr_routing ON: router hash missing" in problems
    wrong = copy.deepcopy(runs["HELIOS-noLLM"])
    assert st.run_marks(wrong, get_variant("HELIOS-Full"))[0] == (
        "variant_config_hash does not match the variant table"
    )


def test_a_moved_verdict_is_found(runs: dict[str, dict[str, Any]]) -> None:
    moved = copy.deepcopy(runs["HELIOS-noACP"])
    fused = next(s for s in moved["steps"] if s["id"] == "F")
    fused["ranked"] = list(reversed(fused["ranked"]))
    out = st.unchanged_verdicts(
        {"HELIOS-Full": {"c": runs["HELIOS-Full"]}, "HELIOS-noACP": {"c": moved}}
    )
    assert out == {"HELIOS-noACP": {"cases": 1, "differ": ["c"]}}


def test_exercised_marks_fail_only_when_the_corpus_could_show_them() -> None:
    full = get_variant("HELIOS-Full")
    no_graph = {"steps": [{"id": "P:gpipe", "status": "skipped"}]}
    assert st.exercised([(full, no_graph)])["ueg_structural_features"] == {
        "possible": 0,
        "seen": 0,
        "result": "not exercised",
    }
    bare: dict[str, Any] = {
        "steps": [{"id": "P:gpipe", "status": "ranked", "sigma": None, "items": []}]
    }
    assert st.exercised([(full, bare)])["ueg_structural_features"]["result"] == "fail"


def test_parameter_problems() -> None:
    frozen = {"dpipe": "a" * 64}
    entries = [
        {"parameter_hashes": {"dpipe": "b" * 64, "lpipe_model": "x"}},
        {"parameter_hashes": {"dpipe": "a" * 64, "lpipe_model": "y"}},
        {"parameter_hashes": {"lpipe_model": ""}},  # L-pipe did not run
    ]
    assert st.parameter_problems(entries, frozen) == [
        "dpipe: bbbbbbbbbbbb != frozen aaaaaaaaaaaa",
        "lpipe_model: 2 different values",
    ]


# ── completion, refusal and the CLI on a synthetic campaign ─────────────────


def _campaign(
    tmp_path: Path, runs: dict[str, dict[str, Any]], *, drop: str | None = None
) -> Path:
    d = tmp_path / "camp"
    (d / "coe").mkdir(parents=True)
    specs, log = [], []
    refused = {
        "HELIOS-noCogni": "no reader of p4_cognitive outside helios/vcl",
        "HELIOS-HIS3": "no reader of his_tier outside helios/vcl",
    }
    for i, name in enumerate(RUNNABLE):
        phase = "confirmatory" if name in CONFIRMATORY_VARIANTS else "exploratory"
        specs.append({"position": i, "phase": phase, "case": "c1", "system": name})
        if name == drop:
            continue
        key = f"{phase}/c1/{name}"
        rid = runs[name]["run_id"]
        log.append({"event": "started", "key": key, "run_id": rid})
        log.append({"event": "passed", "key": key, "run_id": rid, "gate_check": None})
        (d / "coe" / f"results.{name}.coe.jsonl").write_text(
            json.dumps(runs[name]) + "\n"
        )
    schedule = {"corpus": "fixture", "digest": "d", "specs": specs, "refused": refused}
    (d / "schedule.json").write_text(json.dumps(schedule))
    (d / "campaign_log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in log))
    (d / "exclusion_ledger.jsonl").write_text("")
    return d


def test_the_whole_report_passes_on_a_clean_campaign(
    tmp_path: Path, runs: dict[str, dict[str, Any]]
) -> None:
    report = st.system_report(
        _campaign(tmp_path, runs), ["confirmatory", "exploratory"]
    )
    assert report["completion"]["result"] == "pass"
    assert report["completion"]["events"] == {"passed": 13}
    assert report["refusal"]["result"] == "pass"
    assert report["result"] == "pass"


def test_a_missing_run_and_a_wrong_refusal_fail(
    tmp_path: Path, runs: dict[str, dict[str, Any]]
) -> None:
    d = _campaign(tmp_path, runs, drop="HELIOS-noIOL")
    schedule = json.loads((d / "schedule.json").read_text())
    schedule["refused"]["HELIOS-noFGSV"] = "no reader of fgsv_ks_gate"
    (d / "schedule.json").write_text(json.dumps(schedule))
    report = st.system_report(d, ["confirmatory", "exploratory"])
    assert report["completion"]["missing"] == ["exploratory/c1/HELIOS-noIOL"]
    assert report["refusal"]["result"] == "fail"
    assert report["result"] == "fail"


def test_excluded_runs_need_a_ledger_entry_and_no_inactive_component(
    tmp_path: Path, runs: dict[str, dict[str, Any]]
) -> None:
    d = _campaign(tmp_path, runs)
    with (d / "campaign_log.jsonl").open("a") as fh:
        fh.write(
            json.dumps(
                {
                    "event": "excluded",
                    "key": "confirmatory/c1/HELIOS-D",
                    "run_id": "r-x",
                    "error": "GatedComponentInactiveError",
                }
            )
            + "\n"
        )
    c = st.system_report(d, ["confirmatory", "exploratory"])["completion"]
    assert c["unledgered"] == ["confirmatory/c1/HELIOS-D"]
    assert c["gated_component_inactive"] == 1
    assert c["result"] == "fail"


def test_cli(tmp_path: Path, runs: dict[str, dict[str, Any]]) -> None:
    from bin.system_test import main

    out = tmp_path / "report.json"
    d = _campaign(tmp_path, runs)
    assert main(["--dir", str(d), "--out", str(out), "--no-ledgers"]) == 0
    report = json.loads(out.read_text())
    assert report["result"] == "pass"
    assert set(report["digests"]) == {
        "schedule.json",
        "campaign_log.jsonl",
        "exclusion_ledger.jsonl",
    }
