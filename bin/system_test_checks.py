"""S5.1 system test of every variant (design s5_1_system_test_design.md S-c).

Reads a campaign directory (schedule, campaign log, exclusion ledger, CoE
files) and never ground truth. Five groups of checks:

1. completion: every scheduled spec of the phases run is passed or excluded
   with a ledger entry; no run called a gated component under an OFF flag;
2. refusal: the schedule refuses exactly the no-consumer variants;
3. flag marks: every run shows the visible mark of each ``VCLFlag``'s state
   (S5.2 design D-e), within the interactions S5.2 declares;
4. unchanged verdicts: variants that differ from HELIOS-Full only in recorded
   steps publish Full's pipeline and fused decisions on every case;
5. integrity: variant config hashes and frozen parameter hashes.

Results are exploratory build-data checks; no metric is read here.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from helios.orchestrator.campaign import _state, read_log
from helios.vcl import EXPLORATORY_VARIANTS, VCLFlag, VCLManifest, get_variant
from helios.vcl.disjointness import NO_CONSUMER

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

HELIOS_ENABLE_SYSTEM_TEST: bool = True

#: Exploratory variants that differ from Full only in recorded steps (ACP
#: block, step A, step S, the post-scoring reward replay, step N).
RECORD_ONLY: tuple[str, ...] = (
    "HELIOS-noACP",
    "HELIOS-noFGSV",
    "HELIOS-noIOL",
    "HELIOS-noReconcile",
    "HELIOS-noExpl",
)

# Per-run identity (hashes cover the variant's config hash) and wall time.
_RUN_KEYS = frozenset({"measured", "decision_hash", "refs", "stage1_ms", "terminal_ms"})
_DECISION_STEPS = ("P:dpipe", "P:gpipe", "P:lpipe", "F")


def step(entry: Mapping[str, Any], step_id: str) -> dict[str, Any] | None:
    for s in entry.get("steps", []):
        if s.get("id") == step_id:
            return dict(s)
    return None


def _status(entry: Mapping[str, Any], step_id: str) -> str | None:
    s = step(entry, step_id)
    return None if s is None else s.get("status")


def _has_propagation(entry: Mapping[str, Any]) -> bool:
    d = step(entry, "P:dpipe") or {}
    return any(
        str(i.get("id", "")).endswith(":propagation") for i in d.get("items", [])
    )


def _g_features(entry: Mapping[str, Any]) -> bool | None:
    """None when the G-pipe did not rank; else whether it carried features."""
    g = step(entry, "P:gpipe") or {}
    if g.get("status") != "ranked":
        return None
    return g.get("sigma") is not None or bool(g.get("items"))


# ── 3. flag marks per run ────────────────────────────────────────────────────


def run_marks(entry: Mapping[str, Any], manifest: VCLManifest) -> list[str]:
    """Problems with the visible marks of every flag's state in one run."""
    bad: list[str] = []
    hashes = entry.get("parameter_hashes", {})
    r = step(entry, "R") or {}
    f = step(entry, "F") or {}
    n = step(entry, "N")
    a = step(entry, "A") or {}

    def need(cond: bool, flag: VCLFlag, what: str) -> None:
        if not cond:
            state = "ON" if getattr(manifest, flag.value) else "OFF"
            bad.append(f"{flag.value} {state}: {what}")

    if entry.get("variant_config_hash") != manifest.compute_variant_config_hash():
        bad.append("variant_config_hash does not match the variant table")

    d_status = _status(entry, "P:dpipe")
    if manifest.dpipe:
        need(d_status != "skipped", VCLFlag.DPIPE, "D-pipe skipped")
    else:
        need(d_status == "skipped", VCLFlag.DPIPE, f"D-pipe {d_status}")

    # Declared interaction: the G-pipe needs a graph (gpipe + l2b_graph).
    g_allowed = manifest.gpipe and manifest.l2b_graph
    if g_allowed:
        need(r.get("reason") != "gpipe_off", VCLFlag.GPIPE, "routing says gpipe_off")
    else:
        flag = VCLFlag.GPIPE if not manifest.gpipe else VCLFlag.L2B_GRAPH
        need(_status(entry, "P:gpipe") == "skipped", flag, "G-pipe not skipped")
        need(r.get("reason") == "gpipe_off", flag, f"routing reason {r.get('reason')}")
    if not manifest.l2b_graph:
        need(
            not _has_propagation(entry),
            VCLFlag.L2B_GRAPH,
            "propagation without a graph",
        )

    if not manifest.ueg_structural:
        need(
            _g_features(entry) is not True,
            VCLFlag.UEG_STRUCTURAL,
            "G-pipe carried trace features",
        )
    if not manifest.dpipe_propagation:
        need(
            not _has_propagation(entry),
            VCLFlag.DPIPE_PROPAGATION,
            "propagation evidence present",
        )

    l_status = _status(entry, "P:lpipe")
    if manifest.l2c_llm:
        if r.get("mode") == "uniform":
            need(
                l_status != "skipped", VCLFlag.L2C_LLM, "uniform run skipped the L-pipe"
            )
        if n is not None:
            need(n.get("narrator") == "llm", VCLFlag.L2C_LLM, "template narrator")
    else:
        need(l_status == "skipped", VCLFlag.L2C_LLM, f"L-pipe {l_status}")
        need("lpipe_model" not in hashes, VCLFlag.L2C_LLM, "lpipe_model hash present")
        if n is not None:
            need(n.get("narrator") == "template", VCLFlag.L2C_LLM, "LLM narrator")

    expected = "mahc" if manifest.mahc_hierarchical else "vote_only"
    need(
        f.get("method") == expected,
        VCLFlag.MAHC_HIERARCHICAL,
        f"fusion {f.get('method')}",
    )

    if manifest.cbr_routing:
        need(r.get("mode") == "routed", VCLFlag.CBR_ROUTING, f"mode {r.get('mode')}")
        need("router" in hashes, VCLFlag.CBR_ROUTING, "router hash missing")
    else:
        need(r.get("mode") == "uniform", VCLFlag.CBR_ROUTING, f"mode {r.get('mode')}")
        need("router" not in hashes, VCLFlag.CBR_ROUTING, "router hash present")

    acp = (r.get("acp") or {}).get("status")
    if manifest.acp_stateful:
        need(acp not in (None, "off"), VCLFlag.ACP_STATEFUL, f"ACP status {acp}")
    else:
        need(acp == "off", VCLFlag.ACP_STATEFUL, f"ACP status {acp}")
        need("acp" not in hashes, VCLFlag.ACP_STATEFUL, "acp hash present")

    if manifest.coe_narrative:
        need(n is not None, VCLFlag.COE_NARRATIVE, "no step N")
    else:
        need(n is None, VCLFlag.COE_NARRATIVE, "step N present")
        need(
            "narrator_params" not in hashes,
            VCLFlag.COE_NARRATIVE,
            "narrator hash present",
        )

    if manifest.fgsv_ks_gate:
        need(
            a.get("fgsv") is True, VCLFlag.FGSV_KS_GATE, f"step A fgsv={a.get('fgsv')}"
        )
    else:
        need(
            (a.get("fgsv"), a.get("verdict"), a.get("reason"))
            == (False, "UNVALIDATED", "fgsv_off"),
            VCLFlag.FGSV_KS_GATE,
            f"step A {a.get('verdict')}/{a.get('reason')}",
        )

    has_s = step(entry, "S") is not None
    if manifest.iol_self_telemetry:
        need(has_s, VCLFlag.IOL_SELF_TELEMETRY, "no step S")
    else:
        need(not has_s, VCLFlag.IOL_SELF_TELEMETRY, "step S present")
    # reconcile_terminal leaves no in-run mark: the E-H5 replay reads it after
    # scoring; in-run, noReconcile must equal Full (unchanged_verdicts).
    return bad


def exercised(
    entries: Iterable[tuple[VCLManifest, Mapping[str, Any]]],
) -> dict[str, Any]:
    """Corpus-level ON marks that only some cases can show (traces, graphs).

    A mark the corpus cannot show is "not exercised", never a failure; a mark
    it can show but no run shows is a failure.
    """
    g_ranked = g_feat = prop_possible = prop_seen = l_ranked = l_on = 0
    for manifest, entry in entries:
        feats = _g_features(entry)
        if manifest.ueg_structural and feats is not None:
            g_ranked += 1
            g_feat += bool(feats)
        if manifest.dpipe_propagation and manifest.l2b_graph and feats is not None:
            prop_possible += 1
            prop_seen += _has_propagation(entry)
        if manifest.l2c_llm:
            l_on += 1
            l_ranked += _status(entry, "P:lpipe") == "ranked"

    def mark(possible: int, seen: int) -> str:
        if not possible:
            return "not exercised"
        return "pass" if seen else "fail"

    # Propagation evidence is recorded only where propagation changes a
    # score, so its ON mark depends on the data: reported, never failed (its
    # OFF mark is enforced per run).
    prop = "not exercised" if not prop_possible else "reported"

    return {
        "ueg_structural_features": {
            "possible": g_ranked,
            "seen": g_feat,
            "result": mark(g_ranked, g_feat),
        },
        "dpipe_propagation": {
            "possible": prop_possible,
            "seen": prop_seen,
            "result": prop,
        },
        "l2c_llm_ranked": {
            "possible": l_on,
            "seen": l_ranked,
            "result": mark(l_on, l_ranked),
        },
    }


# ── 4. unchanged verdicts ────────────────────────────────────────────────────


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in _RUN_KEYS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def decision(entry: Mapping[str, Any]) -> list[Any]:
    """The pipeline and fused decisions of a run, without identity or timing."""
    return [_strip(step(entry, sid)) for sid in _DECISION_STEPS]


def unchanged_verdicts(
    by_variant: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """For each record-only variant: cases whose decisions differ from Full's."""
    full = by_variant.get("HELIOS-Full", {})
    out: dict[str, dict[str, Any]] = {}
    for name in RECORD_ONLY:
        runs = by_variant.get(name)
        if runs is None:
            continue
        cases = sorted(set(runs) & set(full))
        differ = [c for c in cases if decision(runs[c]) != decision(full[c])]
        out[name] = {"cases": len(cases), "differ": differ}
    return out


def top1_differences(
    by_variant: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, dict[str, int]]:
    """Per variant: cases whose fused top-1 differs from Full's (a count)."""
    full = by_variant.get("HELIOS-Full", {})

    def top(entry: Mapping[str, Any]) -> str | None:
        ranked = (step(entry, "F") or {}).get("ranked") or []
        return ranked[0] if ranked else None

    return {
        name: {
            "cases": len(set(runs) & set(full)),
            "differ": sum(top(runs[c]) != top(full[c]) for c in set(runs) & set(full)),
        }
        for name, runs in sorted(by_variant.items())
        if name != "HELIOS-Full"
    }


# ── 5. integrity: parameter hashes ───────────────────────────────────────────


def frozen_parameter_hashes() -> dict[str, str]:
    """Hashes of the frozen parameter files, as the runner records them."""
    from helios.acp.params import acp_params_hash, load_acp_params
    from helios.actions.fgsv import fgsv_params_hash, load_fgsv_params
    from helios.consensus.params import load_mahc_params, mahc_params_hash
    from helios.consensus.router_params import load_router_params, router_params_hash
    from helios.narrative.params import load_narrator_params, narrator_params_hash
    from helios.pipelines.d_pipe.params import dpipe_params_hash, load_dpipe_params
    from helios.pipelines.g_pipe.params import gpipe_params_hash, load_gpipe_params
    from helios.telemetry.trigger import detector_hash, load_detector_params

    return {
        "detector": detector_hash(load_detector_params()),
        "dpipe": dpipe_params_hash(load_dpipe_params()),
        "gpipe": gpipe_params_hash(load_gpipe_params()),
        "mahc": mahc_params_hash(load_mahc_params()),
        "router": router_params_hash(load_router_params()),
        "narrator_params": narrator_params_hash(load_narrator_params()),
        "acp": acp_params_hash(load_acp_params()),
        "fgsv": fgsv_params_hash(load_fgsv_params()),
    }


def parameter_problems(
    entries: Iterable[Mapping[str, Any]], frozen: Mapping[str, str]
) -> list[str]:
    """Frozen keys must equal the frozen files; every other key must take one
    non-empty value across the campaign (model digest, prompt hashes)."""
    bad: set[str] = set()
    others: dict[str, set[str]] = {}
    for entry in entries:
        for key, value in entry.get("parameter_hashes", {}).items():
            if key in frozen:
                if value != frozen[key]:
                    bad.add(f"{key}: {str(value)[:12]} != frozen {frozen[key][:12]}")
            elif value:
                others.setdefault(key, set()).add(str(value))
    bad.update(
        f"{k}: {len(v)} different values" for k, v in others.items() if len(v) > 1
    )
    return sorted(bad)


# ── campaign view and the whole report ───────────────────────────────────────


@dataclass
class CampaignView:
    schedule: dict[str, Any]
    final: dict[str, dict[str, Any]]
    open_runs: dict[str, str]
    excluded_run_ids: set[str]
    entries: dict[str, dict[str, Any]]  # run_id -> CoE entry
    phases: list[str] = field(default_factory=list)

    def runs_by_variant(self) -> dict[str, dict[str, dict[str, Any]]]:
        """variant -> case -> CoE entry of the final passed run."""
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for key, rec in self.final.items():
            if rec.get("event") != "passed" or rec.get("gate_check"):
                continue
            entry = self.entries.get(rec.get("run_id", ""))
            if entry is None:
                continue
            _phase, case, system = key.split("/", 2)
            out.setdefault(system, {})[case] = entry
        return out


def load_campaign(directory: Path, phases: Iterable[str]) -> CampaignView:
    schedule = json.loads((directory / "schedule.json").read_text(encoding="utf-8"))
    state = _state(read_log(directory / "campaign_log.jsonl"))
    excluded = {
        str(r.get("run_id"))
        for r in read_log(directory / "exclusion_ledger.jsonl")
        if r.get("run_id")
    }
    entries: dict[str, dict[str, Any]] = {}
    for path in sorted((directory / "coe").glob("*.coe.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                e = json.loads(line)
                entries[str(e["run_id"])] = e
    return CampaignView(
        schedule, state.final, state.open_run, excluded, entries, list(phases)
    )


def completion(view: CampaignView) -> dict[str, Any]:
    specs = [s for s in view.schedule["specs"] if s["phase"] in view.phases]
    events: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    gate: Counter[str] = Counter()
    missing: list[str] = []
    unledgered: list[str] = []
    for s in specs:
        key = f"{s['phase']}/{s['case']}/{s['system']}"
        rec = view.final.get(key)
        if rec is None:
            missing.append(key)
            continue
        events[rec["event"]] += 1
        if rec["event"] == "excluded":
            errors[str(rec.get("error"))] += 1
            if rec.get("run_id") not in view.excluded_run_ids:
                unledgered.append(key)
        elif rec.get("gate_check"):
            gate[str(rec["gate_check"])] += 1
    inactive = errors.get("GatedComponentInactiveError", 0)
    ok = not missing and not unledgered and not view.open_runs and not inactive
    ok = ok and set(events) <= {"passed", "excluded"}
    return {
        "scheduled": len(specs),
        "events": dict(events),
        "excluded_by_error": dict(errors),
        "gate_exclusions": dict(gate),
        "missing": missing[:20],
        "missing_count": len(missing),
        "unledgered": unledgered,
        "open_runs": sorted(view.open_runs),
        "gated_component_inactive": inactive,
        "result": "pass" if ok else "fail",
    }


def refusal(schedule: Mapping[str, Any]) -> dict[str, Any]:
    refused = dict(schedule.get("refused", {}))
    expected = {}
    for name in EXPLORATORY_VARIANTS:
        manifest = get_variant(name)
        full = get_variant("HELIOS-Full")
        off = {
            f.value
            for f in VCLFlag.bool_flags()
            if getattr(manifest, f.value) != getattr(full, f.value)
        }
        if off and off <= {f.value for f in NO_CONSUMER}:
            expected[name] = sorted(off)
    ok = set(refused) == set(expected) and all(
        all(flag in refused[n] for flag in flags) for n, flags in expected.items()
    )
    return {
        "refused": refused,
        "expected": expected,
        "result": "pass" if ok else "fail",
    }


def system_report(directory: Path, phases: Iterable[str]) -> dict[str, Any]:
    view = load_campaign(directory, phases)
    by_variant = view.runs_by_variant()
    marks: dict[str, dict[str, Any]] = {}
    pairs: list[tuple[VCLManifest, dict[str, Any]]] = []
    for name, runs in sorted(by_variant.items()):
        manifest = get_variant(name)
        problems: Counter[str] = Counter()
        for entry in runs.values():
            pairs.append((manifest, entry))
            problems.update(run_marks(entry, manifest))
        marks[name] = {"runs": len(runs), "problems": dict(problems)}
    unchanged = unchanged_verdicts(by_variant)
    corpus = exercised(pairs)
    params = parameter_problems(
        (e for runs in by_variant.values() for e in runs.values()),
        frozen_parameter_hashes(),
    )
    report: dict[str, Any] = {
        "corpus": view.schedule.get("corpus"),
        "schedule_digest": view.schedule.get("digest"),
        "phases": view.phases,
        "completion": completion(view),
        "refusal": refusal(view.schedule),
        "flag_marks": marks,
        "exercised": corpus,
        "unchanged_verdicts": unchanged,
        "top1_differs_from_full": top1_differences(by_variant),
        "parameter_problems": params,
    }
    failed = [
        report["completion"]["result"] != "pass",
        report["refusal"]["result"] != "pass",
        any(m["problems"] for m in marks.values()),
        any(v["result"] == "fail" for v in corpus.values()),
        any(u["differ"] for u in unchanged.values()),
        bool(params),
    ]
    report["result"] = "fail" if any(failed) else "pass"
    return report
