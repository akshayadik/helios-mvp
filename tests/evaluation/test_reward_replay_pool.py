"""E-H5 pool replay (design eh5_pool_replay_design.md P-a..P-e; entry 110)."""

from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING, Any

import duckdb
import pytest

from bin.reward_replay import POOL_COE, pool_cases, pool_subset, prewarm
from helios.consensus.mahc import Vote
from helios.consensus.router_params import SELECTABLE, Arm
from helios.evaluation.reward_replay import (
    BUILD_MEASURE,
    Decision,
    ThawedRouter,
    full_information_rows,
    rre_by_case_stream,
    single_draws,
    state_gap,
    terminal_reward,
)
from helios.telemetry.pool_lock import PoolLockedError
from helios.vcl import VCLFlag, get_variant  # noqa: F401
from tests.evaluation.test_reward_replay import CASES, FROZEN, MAHC, _case

if TYPE_CHECKING:
    from pathlib import Path


def test_terminal_reward_measure_is_selectable() -> None:
    # D ranks the root second: an HR@3 hit, not an HR@1 hit.
    base = _case(1, "g")
    case = dataclasses.replace(
        base,
        votes={**base.votes, "dpipe": Vote("dpipe", ("svc-x", base.root), 0.3)},
    )
    assert terminal_reward(case, Arm.D, MAHC, "hr_at_3") == 1
    assert terminal_reward(case, Arm.D, MAHC, "hr_at_1") == 0
    assert terminal_reward(case, Arm.D, MAHC) == 1  # build default stays HR@3
    assert BUILD_MEASURE == "hr_at_3"
    with pytest.raises(ValueError, match="unknown reward measure"):
        terminal_reward(case, Arm.D, MAHC, "mrr")


def test_build_rows_unchanged_by_default() -> None:
    idx = list(range(len(CASES)))
    assert full_information_rows(CASES, idx, MAHC) == full_information_rows(
        CASES, idx, MAHC, "hr_at_3"
    )


def test_single_draws_are_seeded_permutations() -> None:
    a = single_draws(0, 12)
    assert a == single_draws(0, 12)
    assert a != single_draws(1, 12)
    assert sorted(a.order) == list(range(12))
    assert len(a.gaps) == len(a.r1_delay_s) == len(a.r2_delay_s) == 12
    assert all(60 <= d <= 300 for d in a.r1_delay_s)


def test_state_gap_and_prewarm() -> None:
    assert state_gap(FROZEN, FROZEN) == 0
    rows, gap = prewarm(CASES, FROZEN, MAHC)
    warmed = ThawedRouter(FROZEN, rows).params()
    assert state_gap(warmed, warmed) == 0
    assert gap == pytest.approx(state_gap(warmed, FROZEN))
    # The toy cases are not the build cases: their fit differs from the frozen one.
    assert gap > 0
    assert set(rows) == set(SELECTABLE)


def test_rre_by_case_stream_keys_and_skips() -> None:
    def d(case: int, r1: float | None, r2: int) -> Decision:
        return Decision(case, case, "pool", Arm.D_L, Arm.D_L, False, r2, r1, r2)

    out = rre_by_case_stream(
        [d(0, 0.95, 1), d(1, 0.95, 0), d(2, None, 1)], CASES, 0.8, "s3"
    )
    assert out == {
        f"{CASES[0].incident_id}|s3": 0,
        f"{CASES[1].incident_id}|s3": 1,
    }


# ── the CLI's pool path (P-a, P-b) ──────────────────────────────────────────


def _entry(incident: str, variant: str, *, featured: bool = True) -> dict[str, Any]:
    c = _case(int(incident[-3:]), "g")
    routing: dict[str, Any] = {"id": "R", "ran": True}
    if featured:
        routing.update(features_cheap=list(c.x_cheap), features=list(c.x_dg or ()))
    steps: list[dict[str, Any]] = [
        {"id": "T", "signal": "latency"},
        routing,
    ]
    for name, vote in c.votes.items():
        steps.append(
            {
                "id": f"P:{name}",
                "status": "ranked",
                "ranked": list(vote.ranked),
                "sigma": vote.sigma,
                "measured": {"latency_ms": c.latency_ms[name]},
            }
        )
    return {
        "incident_id": incident,
        "variant_config_hash": get_variant(variant).compute_variant_config_hash(),
        "steps": steps,
    }


def _campaign(
    tmp_path: Path, *, scored: bool = True, subset: list[str] | None = None
) -> Path:
    d = tmp_path / "camp"
    (d / "coe").mkdir(parents=True)
    wanted = subset if subset is not None else ["incident001", "incident002"]
    (d / "schedule.json").write_text(
        json.dumps({"eh5_cases": wanted}), encoding="utf-8"
    )
    con = duckdb.connect(str(d / "results.duckdb"))
    con.execute("create table eval_score (run_id text, corpus text)")
    if scored:
        con.execute("insert into eval_score values ('r', 'pool')")
    con.close()
    entries = [
        _entry("incident001", "HELIOS-noRouter"),
        _entry("incident002", "HELIOS-noRouter", featured=False),
        _entry("incident003", "HELIOS-noRouter"),  # outside the subset
        _entry("incident001", "HELIOS-Full"),  # another variant
    ]
    (d / POOL_COE).write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8"
    )
    return d


LABELS = {
    f"incident{i:03d}": {"root_cause_service": f"svc-{i % 4}", "system": "ob"}
    for i in range(1, 4)
}


def test_pool_cases_take_the_subset_from_norouter_entries(tmp_path: Path) -> None:
    camp = _campaign(tmp_path)
    cases, counts = pool_cases(camp, b"k", frozen=lambda: True, labels=LABELS)
    assert [c.incident_id for c in cases] == ["incident001"]
    assert cases[0].corpus == "pool"
    assert counts == {"subset": 2, "found": 2, "missing": 0, "unfeatured": 1}


def test_pool_cases_refuse_without_freeze_or_scoring(tmp_path: Path) -> None:
    with pytest.raises(PoolLockedError):
        pool_cases(_campaign(tmp_path), b"k", frozen=lambda: False, labels=LABELS)
    other = tmp_path / "other"
    other.mkdir()
    unscored = _campaign(other, scored=False)
    with pytest.raises(ValueError, match="not scored"):
        pool_cases(unscored, b"k", frozen=lambda: True, labels=LABELS)


def test_pool_subset_must_exist(tmp_path: Path) -> None:
    camp = _campaign(tmp_path, subset=[])
    with pytest.raises(ValueError, match="no E-H5 subset"):
        pool_subset(camp)
