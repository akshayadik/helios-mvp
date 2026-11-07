"""S3.3 two-stage reward replay (design W-b..W-h; entry 74)."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import numpy as np
import pytest

from helios.consensus.mahc import Vote
from helios.consensus.params import load_mahc_params
from helios.consensus.router_features import FEATURE_NAMES
from helios.consensus.router_params import (
    ROUTER_PARAMS_PATH,
    SELECTABLE,
    Arm,
    load_router_params,
)
from helios.evaluation.reward_replay import (
    Decision,
    ThawedRouter,
    draws,
    features_for,
    full_information_rows,
    halves,
    provisional_reward,
    replay,
    rre,
    terminal_reward,
)
from helios.evaluation.router_calibration import RouterCase, arm_outcomes
from helios.orchestrator.reward_ledger import (
    PROVISIONAL,
    TERMINAL,
    DuplicateRewardError,
    RewardLedger,
    check_pairs,
)
from helios.telemetry.signal_type import SignalType
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401
from helios.vcl.ed25519 import generate_private_key

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"test-secret-at-least-32-chars-long!!"
N = len(FEATURE_NAMES)
MAHC = load_mahc_params()
FROZEN = load_router_params()
_IND = FEATURE_NAMES.index("d_margin")


def _x(ind: float, g: int) -> tuple[float, ...]:
    x: list[float] = [0] * N
    x[0] = 1
    x[_IND] = ind
    x[FEATURE_NAMES.index("g_ran")] = g
    return tuple(x)


def _case(i: int, group: str) -> RouterCase:
    root = f"svc-{i % 4}"
    d_right = i % 3 != 0
    d = (root, "svc-x") if d_right else ("svc-x", "svc-y", "svc-z", "svc-w")
    g = (root,) if i % 2 else ("svc-y", "svc-z", "svc-w")
    return RouterCase(
        incident_id=f"incident{i:03d}",
        corpus="c",
        group=group,
        signal=SignalType.LATENCY,
        x_cheap=_x(int(d_right), 0),
        x_dg=_x(int(d_right), 1),
        graph=True,
        votes={
            "dpipe": Vote("dpipe", d, 0.3),
            "gpipe": Vote("gpipe", g, 0.3),
            "lpipe": Vote("lpipe", (root,), 0.3),
        },
        latency_ms={"dpipe": 200, "gpipe": 900, "lpipe": 12_000},
        root=root,
    )


CASES = [_case(i, f"g{i % 4}") for i in range(24)]
OUTCOMES = [arm_outcomes(c, MAHC) for c in CASES]


def _run(
    tmp_path: Path, variant: str, *, half: int = 0
) -> tuple[list[Decision], RewardLedger, ThawedRouter, list[int]]:
    set_current_manifest(get_variant(variant))
    parts = halves(CASES)
    prewarm = parts[half]
    router = ThawedRouter(FROZEN, full_information_rows(CASES, prewarm, MAHC))
    ledger = RewardLedger(
        KEY,
        tmp_path / f"{variant}.reward.jsonl",
        ed25519_private=generate_private_key(),
    )
    stream = draws(0, parts)[half]
    decisions = replay(
        CASES,
        OUTCOMES,
        stream,
        router,
        MAHC,
        ledger,
        variant=variant,
        label="r0h0",
        mean_gap_s=3_600,
    )
    return decisions, ledger, router, prewarm


def _records(ledger: RewardLedger, stage: str) -> list[dict[str, object]]:
    import json

    lines = ledger._path.read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines if json.loads(x)["stage"] == stage]


def test_halves_keep_groups_whole_and_balanced() -> None:
    a, b = halves(CASES)
    assert sorted(a + b) == list(range(len(CASES)))
    groups_a = {CASES[i].group for i in a}
    groups_b = {CASES[i].group for i in b}
    assert not groups_a & groups_b
    assert len(a) == len(b)


def test_draws_are_seeded_and_cover_the_other_half() -> None:
    parts = halves(CASES)
    first = draws(0, parts)
    assert first == draws(0, parts)
    assert first != draws(1, parts)
    assert sorted(first[0].order) == parts[1]
    assert sorted(first[1].order) == parts[0]
    assert all(60 <= d <= 300 for d in first[0].r1_delay_s)


def test_rewards() -> None:
    case = CASES[1]
    assert provisional_reward(case, Arm.D, MAHC) is None  # R-e
    r1 = provisional_reward(case, Arm.D_G, MAHC)
    assert r1 is not None and 0 <= r1 <= 1
    assert terminal_reward(case, Arm.FULL, MAHC) == OUTCOMES[1][Arm.FULL]


def test_full_replay_pairs_verify_and_ledger_is_signed(tmp_path: Path) -> None:
    decisions, ledger, _, _ = _run(tmp_path, "HELIOS-Full")
    assert len(decisions) == len(CASES) // 2
    assert ledger.verify()[0]
    assert check_pairs(ledger._path) is None
    terminals = _records(ledger, TERMINAL)
    assert terminals and all(t["reconcile_terminal"] for t in terminals)


def test_no_reconcile_writes_no_terminal_record(tmp_path: Path) -> None:
    _, ledger, _, _ = _run(tmp_path, "HELIOS-noReconcile")
    assert _records(ledger, PROVISIONAL)
    assert _records(ledger, TERMINAL) == []
    assert check_pairs(ledger._path) is None


def test_full_state_equals_the_batch_fit_on_terminal_rewards(tmp_path: Path) -> None:
    _, ledger, router, prewarm = _run(tmp_path, "HELIOS-Full")
    rows = full_information_rows(CASES, prewarm, MAHC)
    by_id = {c.incident_id: c for c in CASES}
    for t in _records(ledger, TERMINAL):
        arm = Arm(str(t["arm"]))
        x = features_for(by_id[str(t["case_id"])], arm)
        assert x is not None
        rows[arm].append((x, float(str(t["reward"]))))
    batch = ThawedRouter(FROZEN, rows)
    for arm in SELECTABLE:
        assert np.allclose(router.a[arm], batch.a[arm])
        assert np.allclose(router.b[arm], batch.b[arm])


def test_paired_variants_see_the_same_first_decision(tmp_path: Path) -> None:
    full, *_ = _run(tmp_path, "HELIOS-Full")
    plain, *_ = _run(tmp_path / "n", "HELIOS-noReconcile")
    assert [d.case for d in full] == [d.case for d in plain]
    assert full[0] == plain[0]  # same starting state, no reward arrived yet


def test_a_repeated_reward_is_refused(tmp_path: Path) -> None:
    ledger = RewardLedger(
        KEY, tmp_path / "x.reward.jsonl", ed25519_private=generate_private_key()
    )
    fields = {
        "variant": "HELIOS-Full",
        "stream": "r0h0",
        "case_id": "incident001",
        "arm": "D+G",
        "stage": PROVISIONAL,
        "reward": 0.9,
    }
    ledger.record(fields)
    with pytest.raises(DuplicateRewardError):
        ledger.record(fields)
    reopened = RewardLedger(
        KEY, tmp_path / "x.reward.jsonl", ed25519_private=generate_private_key()
    )
    with pytest.raises(DuplicateRewardError):
        reopened.record(fields)


def _raw(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    ledger = RewardLedger(
        KEY, tmp_path / "bad.reward.jsonl", ed25519_private=generate_private_key()
    )
    for r in records:
        ledger.append(r)  # bypasses the duplicate guard, as a forger would
    return ledger._path


_BASE: dict[str, object] = {
    "variant": "HELIOS-Full",
    "stream": "r0h0",
    "case_id": "incident001",
    "arm": "D+G",
}
_P = {**_BASE, "stage": PROVISIONAL, "reward": 0.9}
_T = {
    **_BASE,
    "stage": TERMINAL,
    "reward": 0,
    "provisional_reward": 0.9,
    "reconcile_terminal": True,
}


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ([_P, _P], "duplicate"),
        ([_P, _T, {**_P, "arm": "D+G"}], "duplicate"),
        ([_T, _P], "names another provisional"),
        ([_P, {**_T, "provisional_reward": 0.4}], "names another provisional"),
        ([_P, {**_T, "reconcile_terminal": False}], "reconcile_terminal off"),
    ],
)
def test_check_pairs_catches_tampering(
    tmp_path: Path, records: list[dict[str, object]], message: str
) -> None:
    err = check_pairs(_raw(tmp_path, records))
    assert err is not None and message in err


def test_provisional_after_terminal_is_caught(tmp_path: Path) -> None:
    t_alone = {**_T, "provisional_reward": None}
    err = check_pairs(_raw(tmp_path, [t_alone, _P]))
    assert err is not None and "after its terminal" in err


def test_rre_sign_rule() -> None:
    base = Decision(0, 0, "c", Arm.D_G, Arm.D_G, False, 1, None, 1)
    tau = 0.8
    assert rre(base, tau) is None
    assert rre(Decision(0, 0, "c", Arm.D_G, Arm.D_G, False, 1, 0.9, 1), tau) == 0
    assert rre(Decision(0, 0, "c", Arm.D_G, Arm.D_G, False, 0, 0.9, 0), tau) == 1
    assert rre(Decision(0, 0, "c", Arm.D_G, Arm.D_G, False, 1, 0.6, 1), tau) == 1


def test_frozen_router_file_is_untouched(tmp_path: Path) -> None:
    before = hashlib.sha256(ROUTER_PARAMS_PATH.read_bytes()).hexdigest()
    _run(tmp_path, "HELIOS-Full")
    assert hashlib.sha256(ROUTER_PARAMS_PATH.read_bytes()).hexdigest() == before


def test_a_label_before_its_provisional_supersedes_it(tmp_path: Path) -> None:
    """Entry 75: the terminal reward applies whole; the late r1 is dropped."""
    import dataclasses

    set_current_manifest(get_variant("HELIOS-Full"))
    parts = halves(CASES)
    router = ThawedRouter(FROZEN, full_information_rows(CASES, parts[0], MAHC))
    stream = draws(0, parts)[0]
    early = dataclasses.replace(
        stream, r2_delay_s=tuple(d / 10 for d in stream.r1_delay_s)
    )
    ledger = RewardLedger(
        KEY, tmp_path / "e.reward.jsonl", ed25519_private=generate_private_key()
    )
    counts: dict[str, int] = {}
    replay(
        CASES,
        OUTCOMES,
        early,
        router,
        MAHC,
        ledger,
        variant="HELIOS-Full",
        label="r0h0",
        mean_gap_s=3_600,
        counts=counts,
    )
    assert counts["superseded"] > 0
    assert _records(ledger, PROVISIONAL) == []
    terminals = _records(ledger, TERMINAL)
    assert any(t.get("superseded") for t in terminals)
    assert all(t["provisional_reward"] is None for t in terminals)
    assert check_pairs(ledger._path) is None
    # Every terminal applied whole: the state is the batch fit on r2.
    rows = full_information_rows(CASES, parts[0], MAHC)
    by_id = {c.incident_id: c for c in CASES}
    for t in terminals:
        arm = Arm(str(t["arm"]))
        x = features_for(by_id[str(t["case_id"])], arm)
        assert x is not None
        rows[arm].append((x, float(str(t["reward"]))))
    batch = ThawedRouter(FROZEN, rows)
    for arm in SELECTABLE:
        assert np.allclose(router.a[arm], batch.a[arm])
        assert np.allclose(router.b[arm], batch.b[arm])
