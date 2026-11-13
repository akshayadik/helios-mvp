"""S4.10 schedule (O-a, O-b, O-g) and the flag-consumer scan (O-h)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from helios.orchestrator.schedule import (
    BASELINE_SLOTS,
    FIRST_VARIANT,
    TRIGGER_SUFFIX,
    Phase,
    build_schedule,
    confirmatory_order,
    scheduled_by_system,
    stride_subset,
    system_name,
)
from helios.research.analysis_plan import BASELINES
from helios.research.seeds import REGISTER_SIZE, REGISTER_START
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.catalog import flag_readers, flags_off_versus_full, unconsumed_variants
from helios.vcl.variants import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS

REPO = Path(__file__).resolve().parents[2]
# Fixture pool: 240 opaque IDs in sorted order, alternating OB / TT -> 120 each.
ORDER = sorted(hashlib.sha256(f"case{i}".encode()).hexdigest()[:32] for i in range(240))
APPS = {c: ("OB" if i % 2 == 0 else "TT") for i, c in enumerate(ORDER)}
REFUSED = {
    "HELIOS-noCogni": "x",
    "HELIOS-HIS3": "x",
    "HELIOS-noFGSV": "x",
    "HELIOS-noIOL": "x",
}


def test_full_size_schedule_counts() -> None:
    s = build_schedule("pool", ORDER, APPS, refused=REFUSED)
    # 8 x 240; 5 x 240; 3 consumed exploratory x 240; the 5 baselines again
    # with the trigger time (S4.8 B-b); every 10th case per app (12 + 12) x the
    # 8 variants that call the model (5 confirmatory + 3) and the 5 baselines.
    assert s.counts() == {
        Phase.CONFIRMATORY: 1920,
        Phase.BASELINE: 1200,
        Phase.EXPLORATORY: 720,
        Phase.BASELINE_TRIGGER: 1200,
        Phase.RERUN: 192 + 120,
    }
    assert len(s.rerun_cases) == 24
    assert len(s.eh5_cases) == 60  # every 4th per app: 30 + 30
    assert sum(APPS[c] == "OB" for c in s.eh5_cases) == 30


def test_schedule_is_pure_and_its_digest_covers_everything() -> None:
    a = build_schedule("pool", ORDER, APPS, refused=REFUSED)
    b = build_schedule("pool", list(ORDER), dict(APPS), refused=dict(REFUSED))
    assert a.to_json() == b.to_json()
    assert json.loads(a.to_json())["digest"] == a.digest
    c = build_schedule("pool", ORDER, APPS, refused={})
    assert c.digest != a.digest
    assert c.counts()[Phase.EXPLORATORY] == 7 * 240


def test_seeds_are_registered_and_unique_outside_the_rerun() -> None:
    s = build_schedule("pool", ORDER, APPS, refused=REFUSED)
    repeats = (Phase.RERUN, Phase.BASELINE_TRIGGER)
    seeds = [x.seed for x in s.specs if x.phase not in repeats]
    assert len(set(seeds)) == len(seeds)
    assert all(REGISTER_START <= x < REGISTER_START + REGISTER_SIZE for x in seeds)
    first = {(x.case, x.system): x.seed for x in s.specs if x.phase not in repeats}
    for x in s.specs:
        if x.phase in repeats:  # the rerun and the trigger row reuse the seed
            assert x.seed == first[x.case, x.system]


def test_case_major_order_with_norouter_first() -> None:
    s = build_schedule("pool", ORDER[:4], APPS, refused=REFUSED)
    conf = [x for x in s.specs if x.phase == Phase.CONFIRMATORY]
    assert [x.case for x in conf[:8]] == [ORDER[0]] * 8
    assert [x.system for x in conf[:8]] == confirmatory_order()
    assert all(x.system == FIRST_VARIANT for x in conf[::8])
    assert [x.position for x in s.specs] == list(range(len(s.specs)))
    rerun = [x for x in s.specs if x.phase == Phase.RERUN]
    assert all(x.cache == "bypass" for x in rerun)


def test_run_ids_are_deterministic_per_attempt() -> None:
    s = build_schedule("pool", ORDER[:2], APPS, refused=REFUSED)
    spec = s.specs[0]
    assert spec.run_id(s.digest, 0) == spec.run_id(s.digest, 0)
    assert spec.run_id(s.digest, 0) != spec.run_id(s.digest, 1)
    assert len({x.key for x in s.specs}) == len(s.specs)


def test_stride_subset_per_app() -> None:
    order = ["a", "b", "c", "d", "e", "f"]
    apps = {"a": "X", "b": "Y", "c": "X", "d": "X", "e": "Y", "f": "Y"}
    # X: a c d -> 2nd is c; Y: b e f -> 2nd is e.
    assert stride_subset(order, apps, 2) == ("c", "e")
    with pytest.raises(ValueError):
        stride_subset(order, apps, 0)


def test_schedule_refusals() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        build_schedule("pool", [ORDER[0], ORDER[0]], APPS, refused={})
    with pytest.raises(ValueError, match="no system"):
        build_schedule("pool", ["zz"], APPS, refused={})
    with pytest.raises(ValueError, match="confirmatory"):
        build_schedule("pool", ORDER[:2], APPS, refused={"HELIOS-Full": "x"})
    with pytest.raises(ValueError, match="baseline"):
        build_schedule("pool", ORDER[:2], APPS, refused={}, baselines=["B9"])


def test_baseline_slots_map_to_registered_names() -> None:
    assert [system_name(s) for s in BASELINE_SLOTS] == list(BASELINES)
    assert system_name("HELIOS-Full") == "HELIOS-Full"
    s = build_schedule("pool", ORDER[:3], APPS, refused=REFUSED)
    by = scheduled_by_system(json.loads(s.to_json()))
    assert by[BASELINES[0]] == ORDER[:3]
    assert by[BASELINES[0] + TRIGGER_SUFFIX] == ORDER[:3]
    assert len(by) == 8 + 5 + 3 + 5


def test_flag_scan_refuses_exactly_the_unconsumed_variants() -> None:
    readers = flag_readers(REPO)
    refused = unconsumed_variants(list(EXPLORATORY_VARIANTS), readers)
    for name, reason in refused.items():
        for flag in flags_off_versus_full(name):
            if not readers[flag]:
                assert flag in reason
    assert unconsumed_variants(list(CONFIRMATORY_VARIANTS), readers) == {}
    # Every refused variant differs from Full only in flags nobody reads.
    assert all(not any(readers[f] for f in flags_off_versus_full(n)) for n in refused)


def test_flag_scan_on_a_synthetic_tree(tmp_path: Path) -> None:
    (tmp_path / "helios" / "vcl").mkdir(parents=True)
    (tmp_path / "bin").mkdir()
    (tmp_path / "helios" / "a.py").write_text("x = manifest.p4_cognitive\n")
    (tmp_path / "bin" / "b.py").write_text("y = VCLFlag.HIS_TIER\n")
    (tmp_path / "helios" / "vcl" / "c.py").write_text("z = m.fgsv_ks_gate\n")
    readers = flag_readers(tmp_path)
    assert readers["p4_cognitive"] == ["helios/a.py"]
    assert readers["his_tier"] == ["bin/b.py"]
    assert readers["fgsv_ks_gate"] == []  # helios/vcl is the flag system itself
    refused = unconsumed_variants(["HELIOS-noCogni", "HELIOS-noFGSV"], readers)
    assert list(refused) == ["HELIOS-noFGSV"]
