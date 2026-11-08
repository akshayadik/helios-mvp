"""S3.2 Action-Class Predictor: features, tier, parameters, block, leakage."""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from helios.acp.features import (
    ACP_FEATURE_NAMES,
    BlastTier,
    MetricFamily,
    acp_features,
    blast_radius_tier,
    metric_family,
)
from helios.acp.params import (
    ACP_CLASSES,
    ACPParams,
    acp_params_from_dict,
    acp_params_hash,
    load_acp_params,
    write_acp_params,
)
from helios.acp.predictor import acp_block, uniform_prior
from helios.schemas.ueg_c import (
    EdgeType,
    NodeType,
    UEGCEdge,
    UEGCNode,
    UEGCSnapshot,
)
from helios.telemetry.signal_type import SignalType, classify
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

D = len(ACP_FEATURE_NAMES)
K = len(ACP_CLASSES)


def _snap(calls: list[tuple[str, str]], anomaly: int = 0) -> UEGCSnapshot:
    services = sorted({s for pair in calls for s in pair} | {"lonely"})
    edges = [
        UEGCEdge(source=a, target=b, edge_type=EdgeType.CALL, weight=1)
        for a, b in calls
    ]
    edges += [
        UEGCEdge(
            source=services[0],
            target=services[-1],
            edge_type=EdgeType.ANOMALY_CO_MOVES,
            weight=1,
        )
        for _ in range(anomaly)
    ]
    return UEGCSnapshot(
        incident_id="inc",
        variant_config_hash="h",
        nodes=[
            UEGCNode(node_id=s, node_type=NodeType.SERVICE, service_name=s)
            for s in services
        ],
        edges=edges,
        captured_at_iso="2026-11-08T00:00:00Z",
    )


def _params(bias: tuple[float, ...] = (0, 0, 0, 0)) -> ACPParams:
    return ACPParams(
        feature_names=ACP_FEATURE_NAMES,
        classes=ACP_CLASSES,
        mean=(0,) * D,
        scale=(1,) * D,
        weights=tuple((b,) + (0,) * (D - 1) for b in bias),
        lam=1,
        n_cases=3,
    )


# --- metric family -----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "family"),
    [
        ("http_server_error_rate", MetricFamily.ERROR),
        ("request_duration_p99", MetricFamily.LATENCY),
        ("container_network_receive_bytes", MetricFamily.NETWORK),
        ("socket_count", MetricFamily.NETWORK),
        ("container_memory_usage_bytes", MetricFamily.MEMORY),
        ("jvm_gc_pause", MetricFamily.MEMORY),
        ("disk_write_bytes", MetricFamily.DISK),
        ("container_cpu_usage", MetricFamily.CPU),
        ("queue_size", MetricFamily.UNKNOWN),
        (None, MetricFamily.UNKNOWN),
        ("", MetricFamily.UNKNOWN),
    ],
)
def test_metric_family(name: str | None, family: MetricFamily) -> None:
    assert metric_family(name) == family


@pytest.mark.parametrize("name", ["error_count", "latency_ms", "duration_fail"])
def test_family_agrees_with_signal_type_on_error_and_latency(name: str) -> None:
    sig = classify(name)
    fam = metric_family(name)
    assert (sig == SignalType.ERROR) == (fam == MetricFamily.ERROR)
    assert (sig == SignalType.LATENCY) == (fam == MetricFamily.LATENCY)


# --- features ----------------------------------------------------------------


def test_features_vector_layout() -> None:
    graph = _snap([("front", "cart"), ("cart", "redis")], anomaly=2)
    x = acp_features(
        signal=SignalType.RESOURCE,
        family=MetricFamily.MEMORY,
        has_logs=True,
        has_traces=True,
        graph=graph,
        d_ranked=["cart", "redis"],
        d_scores={"cart": 3, "redis": 1},
    )
    named = dict(zip(ACP_FEATURE_NAMES, x, strict=True))
    assert len(x) == D
    assert named["bias"] == 1
    assert named["signal_resource"] == 1
    assert named["signal_latency"] == named["signal_error"] == 0
    assert named["has_logs"] == named["has_traces"] == 1
    assert named["log_services"] == round(math.log1p(4), 6)
    assert named["log_call_edges"] == round(math.log1p(2), 6)
    assert named["log_anomaly_edges"] == round(math.log1p(2), 6)
    assert named["d_top1_share"] == 0.75
    assert named["family_memory"] == 1
    assert sum(v for k, v in named.items() if k.startswith("family_")) == 1


def test_features_without_graph_or_ranking() -> None:
    x = acp_features(
        signal=SignalType.UNCLASSIFIED,
        family=MetricFamily.UNKNOWN,
        has_logs=False,
        has_traces=False,
        graph=None,
        d_ranked=[],
        d_scores={},
    )
    assert x == (1,) + (0,) * (D - 1)


def test_non_snapshot_graph_counts_as_none() -> None:
    a = acp_features(
        signal=SignalType.ERROR,
        family=MetricFamily.ERROR,
        has_logs=True,
        has_traces=True,
        graph=object(),
        d_ranked=["a"],
        d_scores={"a": -1},
    )
    named = dict(zip(ACP_FEATURE_NAMES, a, strict=True))
    assert named["log_services"] == 0
    assert named["d_top1_share"] == 0  # non-positive scores give zero


# --- blast-radius tier -------------------------------------------------------


def test_blast_tiers_follow_transitive_callers() -> None:
    chain = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "f"), ("f", "g")]
    graph = _snap(chain)
    assert blast_radius_tier(graph, "a") == BlastTier.ONE  # no callers
    assert blast_radius_tier(graph, "b") == BlastTier.ONE  # a
    assert blast_radius_tier(graph, "c") == BlastTier.TWO  # a, b
    assert blast_radius_tier(graph, "e") == BlastTier.TWO  # a-d
    assert blast_radius_tier(graph, "f") == BlastTier.THREE  # a-e
    assert blast_radius_tier(graph, "g") == BlastTier.THREE


def test_blast_tier_handles_cycles_and_self_calls() -> None:
    graph = _snap([("a", "b"), ("b", "a"), ("b", "b")])
    assert blast_radius_tier(graph, "a") == BlastTier.ONE  # b only


@pytest.mark.parametrize(
    ("graph", "top"),
    [(None, "a"), (object(), "a"), ("calls", None), ("empty", "a")],
)
def test_blast_tier_unknown(graph: object, top: str | None) -> None:
    if graph == "calls":
        graph = _snap([("a", "b")])
    elif graph == "empty":
        graph = _snap([])
    assert blast_radius_tier(graph, top) == BlastTier.UNKNOWN


# --- parameters --------------------------------------------------------------


def test_probabilities_are_a_softmax() -> None:
    probs = _params((2, 0, 0, -1)).probabilities((1,) + (0,) * (D - 1))
    assert set(probs) == set(ACP_CLASSES)
    assert abs(sum(probs.values()) - 1) < 1e-5
    assert max(probs, key=probs.__getitem__) == "resource"


def test_standardise_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="length"):
        _params().probabilities((1, 2))


def test_params_round_trip_and_hash(tmp_path: Path) -> None:
    p = _params((1, 2, 3, 4))
    path = tmp_path / "acp.json"
    write_acp_params(p, path)
    back = load_acp_params(path)
    assert back == p
    assert acp_params_hash(back) == acp_params_hash(p)
    assert acp_params_hash(_params((1, 2, 3, 5))) != acp_params_hash(p)


def test_params_from_dict_refuses_unknown_keys() -> None:
    raw = _params().as_dict()
    raw["extra"] = 1
    with pytest.raises(ValueError, match="keys"):
        acp_params_from_dict(raw)


@pytest.mark.parametrize(
    "change",
    [
        {"feature_names": ("bias",)},
        {"classes": ("a", "b", "c", "d")},
        {"mean": (0,)},
        {"weights": ((0,) * D,)},
        {"scale": (0,) * D},
    ],
)
def test_params_validation(change: dict[str, object]) -> None:
    base = _params().as_dict()
    kwargs: dict[str, object] = {
        "feature_names": tuple(base["feature_names"]),
        "classes": tuple(base["classes"]),
        "mean": tuple(base["mean"]),
        "scale": tuple(base["scale"]),
        "weights": tuple(tuple(r) for r in base["weights"]),
        "lam": 1,
        "n_cases": 3,
    }
    kwargs.update(change)
    with pytest.raises(ValueError, match="ACP"):
        ACPParams(**kwargs)  # type: ignore[arg-type]


# --- block -------------------------------------------------------------------


def test_off_block_is_the_uniform_prior() -> None:
    block = acp_block(on=False, params=_params(), features=None, tier=BlastTier.TWO)
    assert block["status"] == "off"
    assert block["probabilities"] == uniform_prior()
    assert set(uniform_prior().values()) == {0.25}
    assert block["predicted"] is None
    assert block["blast_tier"] == "unknown"


def test_unfit_block_records_features_only() -> None:
    x = (1,) + (0,) * (D - 1)
    block = acp_block(on=True, params=None, features=x, tier=BlastTier.ONE)
    assert block["status"] == "unfit"
    assert block["features"] == list(x)
    assert block["probabilities"] is None
    assert block["blast_tier"] == "1"


def test_predicted_block_and_tie_break() -> None:
    x = (1,) + (0,) * (D - 1)
    tied = acp_block(on=True, params=_params(), features=x, tier=BlastTier.UNKNOWN)
    assert tied["status"] == "predicted"
    assert tied["predicted"] == ACP_CLASSES[0]  # ties go to the first class
    assert tied["params_hash"] == acp_params_hash(_params())
    code = acp_block(
        on=True, params=_params((0, 0, 0, 3)), features=x, tier=BlastTier.ONE
    )
    assert code["predicted"] == "code"


def test_on_block_needs_a_well_formed_vector() -> None:
    with pytest.raises(ValueError, match="feature vector"):
        acp_block(on=True, params=None, features=None, tier=BlastTier.ONE)
    with pytest.raises(ValueError, match="feature vector"):
        acp_block(on=True, params=None, features=(1,), tier=BlastTier.ONE)


# --- leakage -----------------------------------------------------------------

_ACP_DIR = Path(__file__).resolve().parents[2] / "helios" / "acp"


def test_runtime_acp_never_reads_labels() -> None:
    """helios.acp imports no evaluation, adapter or labelling code and names
    no label field (design P-b)."""
    banned_modules = ("helios.evaluation", "helios.adapters", "helios.labelling")
    banned_words = ("ground_truth", "root_cause", "FAULT_CLASS", '"fault"')
    for path in sorted(_ACP_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(banned_modules), path.name
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(banned_modules), path.name
        for word in banned_words:
            assert word not in text, (path.name, word)
