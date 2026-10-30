"""The three G-pipe candidates (S2.2 design §5.2)."""

from __future__ import annotations

import numpy as np
import pytest

from helios.pipelines.g_pipe.features import FEATURE_COLUMNS, GraphFeatures
from helios.pipelines.g_pipe.rankers import (
    LEADER_RESTART_FACTOR,
    RIDGE_LAMBDA,
    LinearRanker,
    plain_ppr,
    weighted_ppr,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.pipelines.test_gpipe_pipeline import _make_snap


def _features(
    services: tuple[str, ...],
    table: list[list[float]] | None = None,
    *,
    wait: dict[tuple[str, str], float] | None = None,
    self_share: dict[str, float] | None = None,
    leaders: frozenset[str] = frozenset(),
) -> GraphFeatures:
    width = len(FEATURE_COLUMNS)
    return GraphFeatures(
        services=services,
        table=np.array(table or [[0] * width for _ in services], dtype="float64"),
        edge_wait_after=wait or {},
        self_share=self_share or {},
        leaders=leaders,
        ghosts=frozenset(),
        onset_bucket={},
        callers_led=dict.fromkeys(services, ()),
        self_shift=dict.fromkeys(services, 0),
    )


def test_constants_are_the_design_values() -> None:
    assert LEADER_RESTART_FACTOR == 2
    assert RIDGE_LAMBDA == 1


def test_plain_ppr_matches_the_previous_traversal() -> None:
    # Recorded from _ppr_traverse before the move (2026-10-29).
    scores = plain_ppr(_make_snap(), {"A": 0.8, "B": 0.2})
    expected = {"A": 0.329489493537, "B": 0.362438752265, "C": 0.308071754198}
    assert scores.keys() == expected.keys()
    for name, value in expected.items():
        assert scores[name] == pytest.approx(value, abs=1e-9)


def test_weighted_ppr_moves_mass_from_victim_to_culprit() -> None:
    f = _features(
        ("A", "B"),
        wait={("A", "B"): 0.95},
        self_share={"A": 0.05, "B": 1},
    )
    scores = weighted_ppr(f, {"A": 1, "B": 0.2})
    assert scores["B"] > scores["A"]


def test_weighted_ppr_leader_restart_doubles() -> None:
    f = _features(("A", "B"), self_share={"A": 1, "B": 1}, leaders=frozenset({"B"}))
    scores = weighted_ppr(f, {"A": 1, "B": 1})
    assert scores["B"] / scores["A"] == pytest.approx(2, rel=1e-4)  # pagerank tol


def _planted(n: int) -> list[tuple[GraphFeatures, str, bool]]:
    """Windows of four services; the root always has the largest wait_pooled."""
    col = FEATURE_COLUMNS.index("wait_pooled")
    out = []
    for w in range(n):
        services = ("s0", "s1", "s2", "s3")
        table = [
            [float((i + j + w) % 3) for j in range(len(FEATURE_COLUMNS))]
            for i in range(4)
        ]
        root = services[w % 4]
        for i in range(4):
            table[i][col] = 2 if services[i] == root else (i + w) % 2
        out.append((_features(services, table), root, False))
    return out


def test_linear_ranker_fit_is_deterministic() -> None:
    assert LinearRanker.fit(_planted(12)) == LinearRanker.fit(_planted(12))


def test_linear_ranker_learns_a_planted_feature() -> None:
    model = LinearRanker.fit(_planted(12))
    weights = np.abs(np.array(model.weights))
    assert int(np.argmax(weights)) == FEATURE_COLUMNS.index("wait_pooled")
    f, root, _ = _planted(13)[12]
    scores = model.score(f)
    assert max(scores, key=scores.__getitem__) == root


def test_linear_ranker_refuses_identity_columns() -> None:
    # A service named like a feature token would let the model key on it.
    examples = [(_features(("error", "b")), "b", False)]
    with pytest.raises(ValueError, match="identity"):
        LinearRanker.fit(examples)
