"""Labelling set builder (S2.9 design §5.3, R-d, R-o): masked items, sealed key,
derived seed, write-once."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

import pytest

from helios.labelling.sets import (
    ARMS,
    build_set,
    derived_seed,
    rater_order,
    write_set,
)
from helios.narrative.params import load_narrator_params
from helios.vcl import VCLFlag, get_variant  # noqa: F401 — flag-guard compliance
from tests.labelling.test_cards import with_step_n
from tests.narrative.test_verifier import ENTRY

if TYPE_CHECKING:
    from pathlib import Path

P = load_narrator_params()
RUBRIC = "r" * 64


def entry(n: int, arm: str = "HELIOS-Full") -> dict[str, Any]:
    e = with_step_n(ENTRY)
    e.update(
        {
            "run_id": f"run-{n:04d}-{arm}",
            "incident_id": f"inc{n:04d}deadbeef",
            "variant_config_hash": get_variant(arm).compute_variant_config_hash(),
            "snapshot_hash": "s" * 64,
            "evaluation_phase": "exploratory",
        }
    )
    return e


def entries(n: int) -> list[dict[str, Any]]:
    return [entry(i, ARMS[i % 2]) for i in range(n)]


def test_set_json_never_names_arm_run_case_or_path(tmp_path: Path) -> None:
    es = entries(6)
    s = build_set(es, planted_share=1 / 4, rubric_sha=RUBRIC, params=P)
    write_set(s, tmp_path / "set")
    text = (tmp_path / "set" / "set.json").read_text("utf-8")
    banned = [*ARMS, "noLLM", "data/", ".parquet", ".coe"]
    banned += [e["run_id"] for e in es] + [e["incident_id"] for e in es]
    for word in banned:
        assert word not in text, word
    key = json.loads((tmp_path / "set" / "key.json").read_text("utf-8"))
    assert {v["arm"] for v in key.values()} == set(ARMS)


def test_seed_is_derived_and_recomputable(tmp_path: Path) -> None:
    es = entries(6)
    a = build_set(es, planted_share=1 / 4, rubric_sha=RUBRIC, params=P)
    b = build_set(copy.deepcopy(es), planted_share=1 / 4, rubric_sha=RUBRIC, params=P)
    write_set(a, tmp_path / "a")
    write_set(b, tmp_path / "b")
    for name in ("set.json", "key.json", "manifest.json"):
        assert (tmp_path / "a" / name).read_bytes() == (
            tmp_path / "b" / name
        ).read_bytes()
    c = build_set(es, planted_share=1 / 4, rubric_sha="q" * 64, params=P)
    assert [i["item"] for i in c.items] != [i["item"] for i in a.items]
    assert a.manifest["seed"] == derived_seed(sorted(a.manifest["sources"]), RUBRIC)


def test_rater_orders_differ_and_cover_all_items() -> None:
    r1, r2 = rater_order(7, "R1", 50), rater_order(7, "R2", 50)
    assert sorted(r1) == sorted(r2) == list(range(50))
    assert r1 != r2 and r1 == rater_order(7, "R1", 50)


def test_set_items_have_one_shape_and_planted_are_spread() -> None:
    s = build_set(entries(32), planted_share=1 / 4, rubric_sha=RUBRIC, params=P)
    assert len(s.items) >= 400
    assert len({tuple(sorted(i)) for i in s.items}) == 1
    planted = [s.key[i["item"]]["planted"] for i in s.items]
    run = longest = 0
    for p in planted:
        run = run + 1 if p else 0
        longest = max(longest, run)
    assert longest <= 6
    share = sum(planted) / len(planted)
    assert abs(share - 1 / 4) < 1 / 50
    assert s.manifest["counts"]["planted"] == sum(planted)


def test_odd_entries_are_skipped_and_counted() -> None:
    no_n = entry(1)
    no_n["steps"] = [st for st in no_n["steps"] if st["id"] != "N"]
    no_rank = copy.deepcopy(entry(2))
    for st in no_rank["steps"]:
        if st["id"] == "F":
            st["ranked"] = []
        if st["id"] == "N":
            st["slots"] = {k: {"claims": []} for k in st["slots"]}
    noexpl = entry(3)
    noexpl["variant_config_hash"] = get_variant(
        "HELIOS-noExpl"
    ).compute_variant_config_hash()
    s = build_set(
        [no_n, no_rank, noexpl, entry(4)],
        planted_share=1 / 4,
        rubric_sha=RUBRIC,
        params=P,
    )
    assert s.manifest["counts"]["skipped"] == 3
    assert s.manifest["counts"]["entries"] == 4


def test_write_once(tmp_path: Path) -> None:
    s = build_set(entries(2), planted_share=1 / 4, rubric_sha=RUBRIC, params=P)
    write_set(s, tmp_path / "set")
    with pytest.raises(FileExistsError):
        write_set(s, tmp_path / "set")
