"""bin/reward_replay.py and verify_ledgers.py --reward (S3.3; entry 74)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from bin import reward_replay as tool
from bin import verify_ledgers as cli
from helios.orchestrator.reward_ledger import PROVISIONAL, TERMINAL, RewardLedger
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import generate_private_key, public_key_pem
from tests.evaluation.test_reward_replay import CASES

if TYPE_CHECKING:
    from pathlib import Path

SECRET = "reward-test-secret-at-least-32-characters"


@pytest.fixture()
def keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Any]:
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", SECRET)
    private = generate_private_key()
    pub = tmp_path / "pub.pem"
    pub.write_bytes(public_key_pem(private))
    monkeypatch.setattr(tool, "load_key", lambda: SECRET.encode())
    monkeypatch.setattr(tool, "load_signer", lambda: private)
    return pub, private


def _verify(directory: Path, pub: Path, *extra: str) -> int:
    return cli.main(["--reward", str(directory), "--public-key", str(pub), *extra])


def test_replays_write_verified_ledgers_and_a_reproducible_report(
    tmp_path: Path, keys: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    pub, _ = keys
    monkeypatch.setattr(tool, "MEAN_GAPS_S", (3_600,))
    first = tool.run_replays(CASES, tmp_path / "a", streams=2)
    second = tool.run_replays(CASES, tmp_path / "b", streams=2)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    names = sorted(p.name for p in (tmp_path / "a").glob("*.reward.jsonl"))
    assert len(names) == 2 * 2 * 2  # variants x streams x halves
    assert first["records"][TERMINAL] > 0
    gap = first["gaps"]["3600"]
    assert set(gap) == {"HELIOS-Full", "HELIOS-noReconcile", "difference"}
    assert gap["HELIOS-Full"]["c"]["cases_per_stream"] == len(CASES)
    assert len(gap["HELIOS-Full"]["c"]["by_decile"]["hr3"]) == tool.DECILES
    assert _verify(tmp_path / "a", pub) == 0
    assert _verify(tmp_path / "a", pub, "--public-only") == 0
    no_reconcile = tmp_path / "a" / "HELIOS-noReconcile-gap3600-r0h0.reward.jsonl"
    assert f'"stage": "{TERMINAL}"' not in no_reconcile.read_text()


def test_verify_reward_fails_on_a_forged_pair(
    tmp_path: Path, keys: tuple[Path, Any]
) -> None:
    pub, private = keys
    (tmp_path / "runs").mkdir()
    ledger = RewardLedger(
        SECRET.encode(), tmp_path / "runs" / "x.reward.jsonl", ed25519_private=private
    )
    base = {"variant": "v", "stream": "r0h0", "case_id": "c1", "arm": "D+G"}
    ledger.append({**base, "stage": PROVISIONAL, "reward": 0.9})
    assert _verify(tmp_path / "runs", pub) == 0
    ledger.append({**base, "stage": PROVISIONAL, "reward": 0.9})  # signed, but a repeat
    assert _verify(tmp_path / "runs", pub) == 1
    assert _verify(tmp_path / "runs", pub, "--public-only") == 1


def test_tool_refuses_pool_without_campaign_and_existing_outputs(
    tmp_path: Path,
) -> None:
    # Entry 110: the pool replay needs a scored campaign; the build replay a run.
    with pytest.raises(SystemExit):
        tool.main(["--corpus", "pool"])
    with pytest.raises(SystemExit):
        tool.main([])
    (tmp_path / "exists").mkdir()
    assert tool.main(["--run", "1", "--out", str(tmp_path / "exists")]) == 2
    pool = ["--corpus", "pool", "--campaign", str(tmp_path), "--out"]
    assert tool.main([*pool, str(tmp_path / "exists")]) == 2


def test_pool_replay_refuses_a_prewarm_off_the_frozen_router(
    tmp_path: Path, keys: tuple[Path, Any]
) -> None:
    # The toy cases are not the build cases, so their fit is not the frozen one.
    with pytest.raises(ValueError, match="differs from the frozen router"):
        tool.run_pool_replay(CASES[:8], CASES, tmp_path / "pool", streams=1)
    assert not (tmp_path / "pool").exists()


def test_pool_replay_report_carries_both_e_h5_forms(
    tmp_path: Path, keys: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    pub, _ = keys
    monkeypatch.setattr(tool, "MEAN_GAPS_S", (3_600,))
    monkeypatch.setattr(tool, "PREWARM_TOLERANCE", float("inf"))
    report = tool.run_pool_replay(CASES[:8], CASES, tmp_path / "pool", streams=2)
    assert report["reward"] == "hr_at_1"
    assert report["cases"] == 8 and report["build_cases"] == len(CASES)
    gap = report["gaps"]["3600"]
    assert set(gap) == {"HELIOS-Full", "HELIOS-noReconcile", "e_h5"}
    assert set(gap["e_h5"]) >= {"registered_form", "same_case_form"}
    names = sorted(p.name for p in (tmp_path / "pool").glob("*.reward.jsonl"))
    assert len(names) == 2 * 2  # variants x streams
    assert _verify(tmp_path / "pool", pub) == 0
    text = json.dumps(report)
    assert "incident0" not in text  # aggregates only, never a case ID
