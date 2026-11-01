"""Training selection and onboarding set (S2.9 design §5.7, R-j)."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from helios.labelling.annotations import CATEGORIES
from helios.labelling.cards import displayed_claims
from helios.labelling.training import onboarding_set, select_training
from helios.narrative.params import load_narrator_params
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.labelling.test_sets import entry

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

P = load_narrator_params()


def _pool() -> list[dict[str, Any]]:
    """Pairs of Full and noLLM entries; only case 7 has a log claim."""
    out = []
    for n in range(12):
        for arm in ("HELIOS-Full", "HELIOS-noLLM"):
            e = entry(n, arm)
            e["incident_id"] = f"case{n:02d}"
            if n != 7:
                for st in e["steps"]:
                    if st["id"] == "N":
                        story = st["slots"]["story"]["claims"]
                        st["slots"]["story"]["claims"] = [
                            c for c in story if c["kind"] != "log_message"
                        ]
            out.append(e)
    return out


def _kinds(entries: Sequence[Mapping[str, Any]]) -> set[str]:
    return {c.kind.value for e in entries for _, _, c in displayed_claims(e)}


def test_selection_covers_every_claim_kind() -> None:
    pool = _pool()
    chosen = select_training(pool, n_per_arm=3, seed=1, exclude_cases=set())
    assert _kinds(chosen) == _kinds(pool)
    assert "case07" in {e["incident_id"] for e in chosen}  # the only log claims
    arms = [e["variant_config_hash"] for e in chosen]
    assert len(chosen) == 6 and len(set(arms)) == 2 and arms.count(arms[0]) == 3


def test_selection_pairs_full_and_nollm_by_case() -> None:
    chosen = select_training(_pool(), n_per_arm=4, seed=2, exclude_cases=set())
    cases = [e["incident_id"] for e in chosen]
    assert all(cases.count(c) == 2 for c in cases)


def test_selection_excludes_earlier_rounds() -> None:
    first = select_training(_pool(), n_per_arm=3, seed=1, exclude_cases=set())
    used = {e["incident_id"] for e in first}
    second = select_training(_pool(), n_per_arm=3, seed=1, exclude_cases=used)
    assert used.isdisjoint({e["incident_id"] for e in second})


def test_selection_is_deterministic() -> None:
    a = select_training(_pool(), n_per_arm=3, seed=9, exclude_cases=set())
    b = select_training(
        copy.deepcopy(_pool()), n_per_arm=3, seed=9, exclude_cases=set()
    )
    assert [e["run_id"] for e in a] == [e["run_id"] for e in b]


def test_onboarding_covers_each_kind_and_category() -> None:
    s = onboarding_set(_pool(), seed=3, params=P)
    real = [i for i in s.items if not s.key[i["item"]]["planted"]]
    planted = [i for i in s.items if s.key[i["item"]]["planted"]]
    assert {i["kind"] for i in real} == _kinds(_pool())
    assert {s.key[i["item"]]["category"] for i in planted} == set(CATEGORIES)
    assert 30 <= len(s.items) <= 50
    assert s.manifest["purpose"] == "onboarding"
