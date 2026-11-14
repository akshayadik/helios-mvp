"""The runner's Tier-2 steps (S4.5-S4.7): step A (proposal, FGSV) and step S
(self-telemetry) are added after the verdict and never change it."""

from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from helios.actions import fgsv
from helios.actions.modes import ActionMode
from helios.integrity_gate import AppendOnlyLedger
from helios.narrative import prompt as narrator_prompt
from helios.narrative.params import load_narrator_params
from helios.orchestrator.runner import RunOrchestrator
from helios.privacy.redact import PII_REDACTION_ENV, RULESET_ID
from helios.telemetry.self_telemetry import Injection, SelfTelemetry
from helios.vcl import VCLFlag, get_variant  # noqa: F401
from tests.pipelines.l_pipe.test_pipeline import OTEL, FakeClient
from tests.test_runner_coe import _step
from tests.test_runner_lpipe import KEY, stage_capture
from tests.test_runner_router import _run

if TYPE_CHECKING:
    from pathlib import Path


# Per-run identity (hashes cover the variant's config hash) and wall time:
# these differ between any two runs, whatever the flags.
_RUN_KEYS = frozenset({"measured", "decision_hash", "refs", "stage1_ms", "terminal_ms"})


def _without(entry: dict[str, Any], step_id: str) -> list[dict[str, Any]]:
    """Steps other than ``step_id``: their decisions, without run identity
    or wall time."""

    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in _RUN_KEYS}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    return [strip(s) for s in entry["steps"] if s["id"] != step_id]


def test_full_and_noiol_publish_the_same_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full, full_calls = _run(tmp_path, monkeypatch, "HELIOS-Full", name="f")
    plain, plain_calls = _run(tmp_path, monkeypatch, "HELIOS-noIOL", name="n")
    assert full_calls == plain_calls
    assert _without(full, "S") == _without(plain, "S")
    assert [s["id"] for s in full["steps"]][-1] == "S"
    assert "S" not in [s["id"] for s in plain["steps"]]
    measured = _step(full, "S")["measured"]
    assert measured["degraded"] is None
    assert measured["run_index"] == 0  # the first run sees no history
    assert measured["self_nodes"] == 6


def test_full_and_nofgsv_differ_only_in_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full, _ = _run(tmp_path, monkeypatch, "HELIOS-Full", name="f")
    plain, _ = _run(tmp_path, monkeypatch, "HELIOS-noFGSV", name="n")
    assert _without(full, "A") == _without(plain, "A")
    a_full, a_plain = _step(full, "A"), _step(plain, "A")
    assert a_full["proposal"] == a_plain["proposal"]
    assert a_full["proposal"]["target"] == _step(full, "F")["ranked"][0]
    assert (a_full["fgsv"], a_full["verdict"], a_full["reason"]) == (
        True,
        "STALE",
        "no_structure",  # the faked graph is no snapshot
    )
    assert a_plain["verdict"] == "UNVALIDATED"
    assert a_full["mode"] == "recommend"
    assert full["parameter_hashes"]["fgsv"] == fgsv.fgsv_params_hash(
        fgsv.load_fgsv_params()
    )
    assert "fgsv" not in plain["parameter_hashes"]


def test_the_action_mode_is_stamped_on_the_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry, _ = _run(tmp_path, monkeypatch, "HELIOS-Full", action_mode=ActionMode.SHADOW)
    assert _step(entry, "A")["mode"] == "shadow"


def test_perturbation_is_recorded_and_a_noop_without_fgsv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain, _ = _run(tmp_path, monkeypatch, "HELIOS-noFGSV", name="n", fgsv_perturb=True)
    assert _step(plain, "A")["verdict"] == "UNVALIDATED"


def test_self_history_and_injection_reach_step_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "self.jsonl"
    inj = Injection("helios.model", "compute_ms", 0, 3)
    _run(
        tmp_path,
        monkeypatch,
        "HELIOS-Full",
        name="a",
        self_telemetry=SelfTelemetry(path=path, injection=inj),
    )
    entry, _ = _run(
        tmp_path,
        monkeypatch,
        "HELIOS-Full",
        name="b",
        self_telemetry=SelfTelemetry(path=path, injection=inj),
    )
    measured = _step(entry, "S")["measured"]
    assert measured["run_index"] == 1  # one earlier run, read back from the file
    assert measured["synthetic_degradation"] == inj.as_dict()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 2
    assert set(rows[0]["metrics"]) >= {"helios.dpipe", "helios.consensus"}


def test_redaction_on_stamps_the_ruleset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PII_REDACTION_ENV, "on")
    entry, _ = _run(tmp_path, monkeypatch, "HELIOS-Full")
    assert entry["parameter_hashes"]["pii_ruleset"] == RULESET_ID
    monkeypatch.delenv(PII_REDACTION_ENV)
    entry, _ = _run(tmp_path, monkeypatch, "HELIOS-Full", name="off")
    assert "pii_ruleset" not in entry["parameter_hashes"]


def _confirmatory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **kw: Any) -> None:
    monkeypatch.setattr(narrator_prompt, "PROVISIONAL", False)
    frozen = dataclasses.replace(load_narrator_params(), provisional=False)
    captures = tmp_path / "captures"
    raw = json.loads(OTEL.read_text())
    raw["evaluation_phase"] = "confirmatory"
    src = tmp_path / "confirmatory_manifest.json"
    src.write_text(json.dumps(raw))
    stage_capture(captures, src)
    orch = RunOrchestrator(
        manifest=get_variant("HELIOS-Full"),
        captures_dir=captures,
        db_path=tmp_path / "r.duckdb",
        registry_path=tmp_path / "r.registry.jsonl",
        reconciliation_path=tmp_path / "r.reconciliation.jsonl",
        exclusion_ledger=MagicMock(spec=AppendOnlyLedger),
        hmac_key=KEY,
        lpipe_client=FakeClient(),  # type: ignore[arg-type]
        narrator_params=frozen,
        **kw,
    )
    orch._reader._pool_lock = lambda _incident: None
    orch.run(captures)


def test_confirmatory_runs_refuse_redaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PII_REDACTION_ENV, "on")
    with pytest.raises(ValueError, match="PII redaction is off in confirmatory"):
        _confirmatory(tmp_path, monkeypatch)


def test_confirmatory_runs_refuse_the_fidelity_break(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(PII_REDACTION_ENV, raising=False)
    with pytest.raises(ValueError, match="exploratory runs only"):
        _confirmatory(tmp_path, monkeypatch, fgsv_perturb=True)
