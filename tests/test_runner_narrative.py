"""The runner narrates every stored run with coe_narrative on (S2.8 §5.6)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from helios.evaluation.cost import incident_usage
from helios.integrity_gate import AppendOnlyLedger
from helios.narrative.claims import Claim
from helios.narrative.params import load_narrator_params
from helios.narrative.verifier import verify
from helios.orchestrator.runner import RunOrchestrator
from helios.telemetry.trigger import ProvisionalParametersError
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401
from tests.pipelines.l_pipe.test_pipeline import OTEL, FakeClient
from tests.test_runner_coe import SIGNER, _entries, _run, _step
from tests.test_runner_lpipe import KEY, stage_capture

if TYPE_CHECKING:
    from pathlib import Path

    from helios.store.result_store import ResultStore

pytestmark = pytest.mark.filterwarnings("ignore::scipy.stats.ConstantInputWarning")
P = load_narrator_params()


class NoModel(FakeClient):
    """Fails on any model call: template-only variants must never call."""

    def generate(self, prompt: str, timeout_s: float) -> Any:
        raise AssertionError("model called")


def _narrative(path: Path) -> dict[str, Any]:
    (entry,) = _entries(path)
    return _step(entry, "N")


def test_full_run_has_llm_narrative_in_coe_entry(tmp_path: Path) -> None:
    store, path = _run(tmp_path)
    step = _narrative(path)
    assert step["narrator"] == "llm"
    # Review I8: an accepted LLM claim travels runner -> store -> ledger.
    story = step["slots"]["story"]
    assert (story["source"], story["attempts"], story["fallback"]) == ("llm", 1, False)
    assert story["claims"][0]["kind"] == "ranking"
    assert any(s["fallback"] for s in step["slots"].values() if s["attempts"])
    (run_id,) = {str(r["run_id"]) for r in store.fetch_all()}
    row = store.fetch_narrative(run_id)
    assert row is not None and row["rendered"] == step["rendered"]
    from helios.orchestrator.coe import CoELedger

    assert CoELedger(KEY, path, ed25519_private=SIGNER).verify()[0]


@pytest.mark.parametrize("variant", ["HELIOS-noLLM", "HELIOS-D", "HELIOS-G"])
def test_nollm_d_g_make_no_model_call(tmp_path: Path, variant: str) -> None:
    captures = tmp_path / "captures"
    stage_capture(captures)
    manifest = get_variant(variant)
    set_current_manifest(manifest)
    RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=tmp_path / "r.duckdb",
        registry_path=tmp_path / "r.registry.jsonl",
        reconciliation_path=tmp_path / "r.reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=KEY,
        lpipe_client=NoModel(),  # type: ignore[arg-type]
        coe_signer=SIGNER,
        coe_path=tmp_path / "x.coe.jsonl",
    ).run(captures)
    step = _narrative(tmp_path / "x.coe.jsonl")
    assert step["narrator"] == "template"
    assert step["cost"] == {"prompt_tokens": 0, "completion_tokens": 0}


def test_noexpl_has_no_narrative(tmp_path: Path) -> None:
    store, path = _run(tmp_path, "HELIOS-noExpl")
    (entry,) = _entries(path)
    assert "N" not in {s["id"] for s in entry["steps"]}
    (run_id,) = {str(r["run_id"]) for r in store.fetch_all()}
    assert store.fetch_narrative(run_id) is None


def test_llm_only_narrates_with_llm(tmp_path: Path) -> None:
    _, path = _run(tmp_path, "HELIOS-LLM-only")
    assert _narrative(path)["narrator"] == "llm"


def test_fused_and_verdict_rows_unchanged_by_narrator(tmp_path: Path) -> None:
    on, _ = _run(tmp_path / "on", "HELIOS-Full")
    off, _ = _run(tmp_path / "off", "HELIOS-noExpl")

    def decisions(store: ResultStore) -> list[Any]:
        rows = sorted(store.fetch_all(), key=lambda r: str(r["pipeline"]))
        return [
            (r["pipeline"], r["ranked_candidates"], r["mu"], r["sigma"]) for r in rows
        ]

    assert decisions(on) == decisions(off)
    (a,) = on.fetch_all_fusion_rows()
    (b,) = off.fetch_all_fusion_rows()
    keep = ("ranked", "scores", "confidence", "fused_sigma", "state")
    assert {k: a[k] for k in keep} == {k: b[k] for k in keep}


def test_every_displayed_claim_verified_and_cited(tmp_path: Path) -> None:
    _, path = _run(tmp_path)
    (entry,) = _entries(path)
    step = _step(entry, "N")
    body = {**entry, "steps": [s for s in entry["steps"] if s["id"] != "N"]}
    for slot in step["slots"].values():
        for raw in slot["claims"]:
            claim = Claim(**raw)
            assert claim.cites
            assert verify(claim, body, P) is None
            assert claim.sentence in step["rendered"]


def test_all_abstained_run_template_header_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from helios.orchestrator import runner as runner_module

    def abstain(**kw: Any) -> dict[str, Any]:
        out = real(**kw)
        return {
            **out,
            "status": "abstained",
            "ranked_candidates": [],
            "candidate_scores": {},
            "mu": None,
            "sigma": None,
            "coe_evidence": {"services": []},
        }

    from helios.pipelines.d_pipe.pipeline import run_dpipe as real

    monkeypatch.setattr(runner_module, "run_dpipe", abstain)
    _, path = _run(tmp_path, "HELIOS-noLLM")
    step = _narrative(path)
    assert step["rendered"].startswith("No suspect ranked")
    assert all(not s["claims"] for s in step["slots"].values())


def test_confirmatory_refuses_provisional_narrator(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    raw = json.loads(OTEL.read_text())
    raw["evaluation_phase"] = "confirmatory"
    src = tmp_path / "m.json"
    src.write_text(json.dumps(raw))
    stage_capture(captures, src)
    manifest = get_variant("HELIOS-noLLM")
    orch = RunOrchestrator(
        manifest=manifest,
        captures_dir=captures,
        db_path=tmp_path / "r.duckdb",
        registry_path=tmp_path / "r.registry.jsonl",
        reconciliation_path=tmp_path / "r.reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=KEY,
        lpipe_client=NoModel(),  # type: ignore[arg-type]
        coe_signer=SIGNER,
    )
    orch._reader._pool_lock = lambda _incident: None
    with pytest.raises(ProvisionalParametersError, match="narrator"):
        orch.run(captures)


def test_cpr_counts_narrator_tokens(tmp_path: Path) -> None:
    store, _ = _run(tmp_path)
    (run_id,) = {str(r["run_id"]) for r in store.fetch_all()}
    verdicts: list[Any] = []
    narrative = store.fetch_narrative(run_id)
    assert narrative is not None
    base = incident_usage(verdicts)
    with_n = incident_usage(verdicts, narrative=narrative)
    assert with_n.prompt_tokens == base.prompt_tokens + narrative["prompt_tokens"]
    assert with_n.completion_tokens == (
        base.completion_tokens + narrative["completion_tokens"]
    )
    assert incident_usage(verdicts, narrative=None) == base


def test_narrator_hashes_in_the_signed_entry(tmp_path: Path) -> None:
    from helios.narrative.params import narrator_params_hash
    from helios.narrative.prompt import NARRATOR_PROMPT_SHA

    _, full = _run(tmp_path / "full")
    _, nollm = _run(tmp_path / "nollm", "HELIOS-noLLM")
    _, noexpl = _run(tmp_path / "noexpl", "HELIOS-noExpl")
    (f,), (n,), (x,) = _entries(full), _entries(nollm), _entries(noexpl)
    params_hash = narrator_params_hash(load_narrator_params())
    assert f["parameter_hashes"]["narrator_params"] == params_hash
    assert f["parameter_hashes"]["narrator_prompt"] == NARRATOR_PROMPT_SHA
    assert n["parameter_hashes"]["narrator_params"] == params_hash
    assert "narrator_prompt" not in n["parameter_hashes"]
    assert "narrator_params" not in x["parameter_hashes"]
