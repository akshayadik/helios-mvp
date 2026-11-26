"""Phase A innovation evidence (scripts/phase_a_evidence.py)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import duckdb
import pytest
from phase_a_evidence import (
    auroc,
    brier,
    calibration,
    expected_calibration_error,
    integrity,
    main,
    narratives,
    render_markdown,
    routing_savings,
)

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS

if TYPE_CHECKING:
    from pathlib import Path


def _run(variant: str, case: str, **kw: Any) -> dict[str, Any]:
    r: dict[str, Any] = {
        "run_id": f"{variant}-{case}",
        "incident_id": case,
        "variant": variant,
        "state": "confirmed",
        "confidence": 0.95,
        "detail": {"contributing": ["dpipe", "lpipe"]},
        "llm_consulted": True,
        "escalated": False,
        "ttt_ms": 200,
        "log_cpr": 3,
        "narrative_claims": 4,
        "grounding_drafted": 6,
        "grounding_rejected": 1,
        "h_struct": 0,
        "h_fact": None,
        "hr_at_1": 1,
        "hr_at_3": 1,
        "pipeline_tokens": 80,
        "narrator": "llm",
        "narr_attempts": 2,
        "narr_fallbacks": 0,
    }
    r.update(kw)
    return r


def test_brier_and_ece() -> None:
    assert brier([], []) is None
    assert brier([1, 0], [1, 0]) == 0
    assert brier([0.75, 0.75], [1, 0]) == pytest.approx(0.3125)
    assert expected_calibration_error([0.95, 0.95, 0.95, 0.95], [1, 1, 1, 0]) == (
        pytest.approx(0.2)
    )


def test_auroc() -> None:
    assert auroc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1
    assert auroc([0.1, 0.2, 0.8, 0.9], [1, 1, 0, 0]) == 0
    assert 2 * (auroc([0.7, 0.7], [1, 0]) or 0) == 1  # a tie counts half
    assert auroc([0.9, 0.8], [1, 1]) is None


def test_calibration_splits_state_by_reason() -> None:
    runs = [
        _run("HELIOS-Full", "a"),
        _run(
            "HELIOS-Full", "b", state="provisional", detail={"contributing": ["dpipe"]}
        ),
        _run("HELIOS-Full", "c", state="provisional", confidence=0.85, hr_at_3=0),
    ]
    by_state = calibration(runs)["HELIOS-Full"]["by_state"]
    assert set(by_state) == {
        "confirmed: two or more pipelines, confidence above floor",
        "provisional: one pipeline ran",
        "provisional: confidence below floor",
    }
    assert by_state["provisional: confidence below floor"]["hr_at_3"] == 0


def test_narratives_rejection_rate() -> None:
    out = narratives(
        [_run("HELIOS-Full", "a"), _run("HELIOS-D", "a", narrator="template")]
    )
    assert out["HELIOS-Full"]["claims_drafted"] == 6
    assert out["HELIOS-Full"]["rejection_rate"] == pytest.approx(1 / 6)
    assert out["HELIOS-D"]["filled_by_template"] == 1


def test_routing_savings_pairs_cases() -> None:
    runs = [
        _run("HELIOS-Full", "a", pipeline_tokens=20, llm_consulted=False),
        _run("HELIOS-Full", "b", pipeline_tokens=40, escalated=True),
        _run("HELIOS-noRouter", "a", pipeline_tokens=60),
        _run("HELIOS-noRouter", "b", pipeline_tokens=60, hr_at_1=0),
        _run("HELIOS-noRouter", "z", pipeline_tokens=999),  # unpaired, ignored
    ]
    out = routing_savings(runs)
    assert out["cases"] == 2
    assert out["HELIOS-Full"]["pipeline_tokens"] == 60
    assert out["HELIOS-noRouter"]["pipeline_tokens"] == 120
    assert 2 * out["tokens_saved_share"] == 1
    assert 2 * out["HELIOS-Full"]["llm_consulted_share"] == 1
    assert 2 * out["hr_at_1_change"] == 1
    assert routing_savings([_run("HELIOS-Full", "a")]) == {"cases": 0}


def test_integrity_counts_final_events(tmp_path: Path) -> None:
    d = tmp_path / "camp"
    d.mkdir()
    events = [
        {"event": "started", "key": "k1"},
        {"event": "excluded", "key": "k1", "gate_check": "baseline_error"},
        {"event": "started", "key": "k2"},
        {"event": "excluded", "key": "k2", "gate_check": "baseline_error"},
        {"event": "passed", "key": "k2"},  # retried and passed
        {"event": "excluded", "key": "k3", "gate_check": "modality_absent"},
    ]
    (d / "campaign_log.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )
    (d / "exclusion_ledger.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    out = integrity([d])
    assert out["run_keys"] == 3
    assert out["by_gate_check"] == {"baseline_error": 1, "modality_absent": 1}
    assert out["ledger_entries_in_these_campaigns"] == 2


def _store(path: Path) -> None:
    full = CONFIRMATORY_VARIANTS["HELIOS-Full"].compute_variant_config_hash()
    con = duckdb.connect(str(path))
    con.execute(
        "create table eval_run (run_id text, incident_id text, "
        "variant_config_hash text, state text, confidence double, "
        "llm_consulted boolean, escalated boolean, ttt_ms double, log_cpr double, "
        "narrative_claims integer, grounding_drafted integer, "
        "grounding_rejected integer, h_struct double, h_fact double)"
    )
    con.execute(
        "create table fusion_row (run_id text, method text, evidence_json text)"
    )
    con.execute(
        "create table eval_score (run_id text, list_kind text, source text, "
        "hr_at_1 integer, hr_at_3 integer)"
    )
    con.execute(
        "create table result_row (run_id text, prompt_tokens integer, "
        "completion_tokens integer)"
    )
    con.execute(
        "create table narrative_row (run_id text, narrator text, attempts integer, "
        "fallbacks integer, prompt_tokens integer, completion_tokens integer)"
    )
    con.execute(
        "insert into eval_run values ('r1', 'c1', ?, 'confirmed', 0.95, true, "
        "false, 200, 3, 4, 6, 0, 0, null), ('b1', 'c1', 'x', 'BASELINE', null, "
        "false, false, 10, 1, 0, 0, 0, 0, null)",
        [full],
    )
    con.execute(
        "insert into fusion_row values ('r1', 'mahc', ?)",
        [json.dumps({"contributing": ["dpipe", "lpipe"]})],
    )
    con.execute(
        "insert into eval_score values ('r1', 'fused', 'mahc', 1, 1), "
        "('r1', 'pipeline', 'dpipe', 0, 1)"
    )
    con.execute("insert into result_row values ('r1', 30, 5), ('r1', 10, 5)")
    con.execute("insert into narrative_row values ('r1', 'llm', 2, 0, 9, 1)")
    con.close()


def test_main_end_to_end(tmp_path: Path) -> None:
    db = tmp_path / "results.duckdb"
    _store(db)
    out_json, out_md = tmp_path / "e.json", tmp_path / "e.md"
    argv = ["--db", str(db), "--out-json", str(out_json), "--out-md", str(out_md)]
    assert main(argv) == 0
    ev = json.loads(out_json.read_text(encoding="utf-8"))
    assert ev["runs"] == 1  # the baseline run is left out
    assert ev["narratives"]["HELIOS-Full"]["claims_drafted"] == 6
    assert ev["calibration"]["HELIOS-Full"]["with_confidence"] == 1
    assert ev["integrity"] is None
    text = render_markdown(ev)
    assert "## Cheap-first routing" in text
    assert "share no case" in text
    assert "c1" not in text  # never a case ID
