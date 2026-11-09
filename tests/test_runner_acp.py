"""The runner records the ACP block and never routes on it (S3.2 P-e, P-f)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from helios.acp.features import ACP_FEATURE_NAMES
from helios.acp.params import ACP_CLASSES, ACPParams, acp_params_hash, write_acp_params
from helios.orchestrator import runner as runner_module
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from tests.test_runner_coe import _step
from tests.test_runner_router import _DECISION_KEYS, _run

if TYPE_CHECKING:
    from pathlib import Path

D = len(ACP_FEATURE_NAMES)


def _params() -> ACPParams:
    return ACPParams(
        feature_names=ACP_FEATURE_NAMES,
        classes=ACP_CLASSES,
        mean=(0,) * D,
        scale=(1,) * D,
        weights=tuple((float(i),) + (0,) * (D - 1) for i in range(len(ACP_CLASSES))),
        lam=1,
        n_cases=4,
    )


@pytest.fixture
def no_frozen_acp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner_module, "ACP_PARAMS_PATH", tmp_path / "absent.json")


@pytest.fixture
def frozen_acp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ACPParams:
    path = tmp_path / "acp_params.json"
    write_acp_params(_params(), path)
    monkeypatch.setattr(runner_module, "ACP_PARAMS_PATH", path)
    return _params()


@pytest.mark.usefixtures("frozen_acp")
@pytest.mark.parametrize("g_top", ["cart", "ad"])
def test_full_routes_and_fuses_exactly_like_no_acp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, g_top: str
) -> None:
    full, full_calls = _run(
        tmp_path, monkeypatch, "HELIOS-Full", g_top=g_top, name=f"f{g_top}"
    )
    plain, plain_calls = _run(
        tmp_path, monkeypatch, "HELIOS-noACP", g_top=g_top, name=f"n{g_top}"
    )
    assert full_calls == plain_calls
    for key in _DECISION_KEYS:
        assert _step(full, "R")[key] == _step(plain, "R")[key], key
    for key in ("ranked", "scores", "confidence", "state", "first_ranked"):
        assert _step(full, "F")[key] == _step(plain, "F")[key], key


def test_full_records_a_prediction_and_its_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, frozen_acp: ACPParams
) -> None:
    entry, _ = _run(tmp_path, monkeypatch, "HELIOS-Full")
    acp = _step(entry, "R")["acp"]
    assert acp["status"] == "predicted"
    assert len(acp["features"]) == D
    assert set(acp["probabilities"]) == set(ACP_CLASSES)
    assert acp["predicted"] in ACP_CLASSES
    assert acp["blast_tier"] == "unknown"  # the faked graph is no snapshot
    assert entry["parameter_hashes"]["acp"] == acp_params_hash(frozen_acp)


@pytest.mark.usefixtures("frozen_acp")
def test_no_acp_records_the_uniform_prior_and_no_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry, _ = _run(tmp_path, monkeypatch, "HELIOS-noACP")
    acp = _step(entry, "R")["acp"]
    assert acp["status"] == "off"
    assert set(acp["probabilities"].values()) == {round(1 / len(ACP_CLASSES), 6)}
    assert "acp" not in entry["parameter_hashes"]


@pytest.mark.usefixtures("no_frozen_acp")
def test_without_frozen_parameters_the_features_are_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry, _ = _run(tmp_path, monkeypatch, "HELIOS-noLLM")
    acp = _step(entry, "R")["acp"]
    assert acp["status"] == "unfit"
    assert len(acp["features"]) == D
    assert acp["probabilities"] is None
    assert "acp" not in entry["parameter_hashes"]


@pytest.mark.usefixtures("frozen_acp")
def test_narrative_does_not_cite_the_acp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full, _ = _run(tmp_path, monkeypatch, "HELIOS-Full", name="nf")
    plain, _ = _run(tmp_path, monkeypatch, "HELIOS-noACP", name="nn")
    n_full, n_plain = _step(full, "N"), _step(plain, "N")
    assert n_full["slots"] == n_plain["slots"]
    assert "acp" not in str(n_full["slots"]).lower()
