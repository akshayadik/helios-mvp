"""G-pipe S2.2: frozen parameters, candidate dispatch, sigma, evidence, noStructural."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from helios.pipelines.g_pipe.features import FEATURE_COLUMNS, GraphFeatures
from helios.pipelines.g_pipe.params import (
    GPipeParams,
    gpipe_params_hash,
    load_gpipe_params,
)
from helios.pipelines.g_pipe.pipeline import evidence_for, gpipe_rank, gpipe_sigma
from helios.pipelines.g_pipe.rankers import LinearRanker, plain_ppr
from helios.vcl import VCLFlag, get_variant, set_current_manifest  # noqa: F401
from tests.pipelines.g_pipe.test_features import (
    DETECTOR,
    T0,
    T_TRIGGER,
    _calls,
    _trigger,
    _window,
)
from tests.pipelines.test_gpipe_pipeline import _make_snap

if TYPE_CHECKING:
    from pathlib import Path

Row = tuple[str, str, str | None, str, float, float]
_WEIGHTED = GPipeParams(ranker="weighted_ppr", model=None, provisional=False)
_SEEDS = {"A": 0.8, "B": 0.2}


def _caller_a(rows: list[Row]) -> list[Row]:
    return [
        (t, s, p, "A" if svc == "a" else svc, lo, hi) for t, s, p, svc, lo, hi in rows
    ]


def _split_rows() -> list[Row]:
    return _caller_a(
        [
            *_calls("t1", T0 + 10, T0 + 12, callee="B"),
            *_calls("t2", T_TRIGGER + 5, T_TRIGGER + 9, callee="B"),
        ]
    )


def test_no_structural_uses_plain_ppr(tmp_path: Path) -> None:
    manifest = get_variant("HELIOS-noStructural")
    set_current_manifest(manifest)
    out = gpipe_rank(
        _make_snap(),
        _SEEDS,
        manifest=manifest,
        window=_window(tmp_path, _split_rows()),
        trigger=_trigger(),
        params=_WEIGHTED,
        detector=DETECTOR,
    )
    assert out.ranker == "ppr"
    assert out.scores == plain_ppr(_make_snap(), _SEEDS)
    assert out.sigma is None


def test_no_split_falls_back_to_plain_ppr(tmp_path: Path) -> None:
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    rows = _caller_a(_calls("t2", T_TRIGGER + 5, T_TRIGGER + 9, callee="B"))
    out = gpipe_rank(
        _make_snap(),
        _SEEDS,
        manifest=manifest,
        window=_window(tmp_path, rows),
        trigger=_trigger(),
        params=_WEIGHTED,
        detector=DETECTOR,
    )
    assert out.ranker == "ppr"
    assert out.scores == plain_ppr(_make_snap(), _SEEDS)


def test_weighted_candidate_runs_with_a_usable_split(tmp_path: Path) -> None:
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    out = gpipe_rank(
        _make_snap(),
        _SEEDS,
        manifest=manifest,
        window=_window(tmp_path, _split_rows()),
        trigger=_trigger(),
        params=_WEIGHTED,
        detector=DETECTOR,
    )
    assert out.ranker == "weighted_ppr"
    assert out.sigma is not None
    assert set(out.scores) == {"A", "B", "C"}


def _features(*, lead: bool, ghost: bool, rise: float) -> GraphFeatures:
    table = np.zeros((2, len(FEATURE_COLUMNS)))
    table[0, FEATURE_COLUMNS.index("wait_pooled_rise")] = rise
    table[0, FEATURE_COLUMNS.index("ghost_in")] = 1 if ghost else 0
    return GraphFeatures(
        services=("B", "A"),
        table=table,
        edge_wait_after={("A", "B"): 0.9},
        self_share={"A": 0.1, "B": 1},
        leaders=frozenset({"B"}) if lead else frozenset(),
        ghosts=frozenset({("A", "B")}) if ghost else frozenset(),
        onset_bucket={},
        callers_led={"B": ("A",) if lead else (), "A": ()},
        self_shift={"B": 2, "A": 0},
    )


def test_sigma_in_unit_interval_and_lower_with_more_evidence() -> None:
    scores = {"B": 0.6, "A": 0.4}
    none = gpipe_sigma(scores, _features(lead=False, ghost=False, rise=0), "B")
    full = gpipe_sigma(scores, _features(lead=True, ghost=True, rise=0.3), "B")
    assert none is not None and full is not None
    assert 0 <= full < none <= 1
    assert gpipe_sigma(scores, None, "B") is None


def test_evidence_has_no_label_or_time_keys() -> None:
    evidence = evidence_for(_features(lead=True, ghost=True, rise=0.3), ["B", "A"])
    text = json.dumps(evidence)
    for banned in ("root", "fault", "inject", "window_start", "window_end", "label"):
        assert banned not in text
    first = evidence["suspects"][0]
    assert first["service"] == "B"
    assert first["wait_from"] == {"A": 0.9}
    assert first["leads"] == ["A"]
    assert first["ghost_edges"] == [["A", "B"]]


def test_params_file_missing_key_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "g.json"
    path.write_text(json.dumps({"ranker": "ppr", "provisional": True}))
    with pytest.raises(ValueError, match="keys"):
        load_gpipe_params(path)


def test_learned_params_need_a_full_model(tmp_path: Path) -> None:
    path = tmp_path / "g.json"
    one = {"weights": [1], "mean": [2], "scale": [1]}
    path.write_text(json.dumps({"ranker": "learned", **one, "provisional": False}))
    with pytest.raises(ValueError, match="per feature"):
        load_gpipe_params(path)


def test_committed_params_are_provisional_plain_ppr_until_selection() -> None:
    params = load_gpipe_params()
    assert params.ranker == "ppr"
    assert params.provisional


def test_params_hash_covers_every_field() -> None:
    n = len(FEATURE_COLUMNS)
    model = LinearRanker(tuple([0.25] * n), tuple([2.5] * n), tuple([3.5] * n))
    base = GPipeParams(ranker="learned", model=model, provisional=False)
    h = gpipe_params_hash(base)
    for changed in (
        replace(base, ranker="weighted_ppr", model=None),
        replace(base, provisional=True),
        replace(base, model=replace(model, weights=tuple([0.75] * n))),
        replace(base, model=replace(model, mean=tuple([1.5] * n))),
        replace(base, model=replace(model, scale=tuple([2.5] * n))),
    ):
        assert gpipe_params_hash(changed) != h


def test_out_of_scope_services_are_never_ranked_or_described(tmp_path: Path) -> None:
    # PR 1 review I2: sigma and evidence must describe the verdict's suspects.
    from helios.schemas.ueg_c import (
        EdgeType,
        NodeType,
        UEGCEdge,
        UEGCNode,
        UEGCSnapshot,
    )

    snap = UEGCSnapshot(
        incident_id="inc-001",
        variant_config_hash="a" * 64,
        nodes=[
            UEGCNode(node_id=s, node_type=NodeType.SERVICE, service_name=s)
            for s in ("A", "B", "flagd")
        ],
        edges=[
            UEGCEdge(source="A", target="flagd", edge_type=EdgeType.CALL, weight=0.9),
            UEGCEdge(source="B", target="flagd", edge_type=EdgeType.CALL, weight=0.9),
        ],
        captured_at_iso="2026-01-01T00:00:00+00:00",
    )
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    out = gpipe_rank(snap, {"A": 0.5, "B": 0.4, "flagd": 0.9}, manifest=manifest)
    assert "flagd" not in out.ranked
    assert "flagd" not in out.scores
    assert out.ranked[0] in {"A", "B"}


def test_ranker_and_fallback_are_always_recorded(tmp_path: Path) -> None:
    # PR 1 review I5: confirmatory runs must be able to count feature fallbacks.
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    out = gpipe_rank(_make_snap(), _SEEDS, manifest=manifest, params=_WEIGHTED)
    assert out.evidence == {"ranker": "ppr", "features": False, "suspects": []}
    rich = gpipe_rank(
        _make_snap(),
        _SEEDS,
        manifest=manifest,
        window=_window(tmp_path, _split_rows()),
        trigger=_trigger(),
        params=_WEIGHTED,
        detector=DETECTOR,
    )
    assert rich.evidence["ranker"] == "weighted_ppr"
    assert rich.evidence["features"] is True
