"""The ACP block recorded in the CoE routing step (S3.2 design P-e, P-f).

With ``acp_stateful`` ON and frozen parameters, the block holds the class
probabilities, the predicted class and the blast-radius tier. With the flag
OFF (HELIOS-noACP) it holds Ch3's uniform prior and tier ``unknown``. The
frozen router never reads this block and the narrator never cites it: the
confirmatory path is unchanged by the ACP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from helios.acp.features import ACP_FEATURE_NAMES, BlastTier
from helios.acp.params import ACP_CLASSES, acp_params_hash
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

    from helios.acp.params import ACPParams

__all__ = ["acp_block", "uniform_prior"]

HELIOS_ENABLE_ACP_PREDICTOR: bool = True

_DIGITS = 6


def uniform_prior() -> dict[str, float]:
    """Ch3's noACP replacement: every class equally likely."""
    return {c: round(1 / len(ACP_CLASSES), _DIGITS) for c in ACP_CLASSES}


def acp_block(
    *,
    on: bool,
    params: ACPParams | None,
    features: Sequence[float] | None,
    tier: BlastTier,
) -> dict[str, Any]:
    """The routing step's ``acp`` record.

    ``status`` is ``off`` (flag OFF), ``unfit`` (flag ON, no frozen
    parameters yet: features recorded, no prediction) or ``predicted``.
    """
    if not on:
        return {
            "status": "off",
            "probabilities": uniform_prior(),
            "predicted": None,
            "blast_tier": BlastTier.UNKNOWN.value,
        }
    if features is None or len(features) != len(ACP_FEATURE_NAMES):
        raise ValueError("ACP is on but its feature vector is missing or malformed")
    block: dict[str, Any] = {
        "features": list(features),
        "blast_tier": tier.value,
    }
    if params is None:
        return {"status": "unfit", **block, "probabilities": None, "predicted": None}
    probs = params.probabilities(features)
    predicted = max(ACP_CLASSES, key=lambda c: (probs[c], -ACP_CLASSES.index(c)))
    return {
        "status": "predicted",
        **block,
        "probabilities": probs,
        "predicted": predicted,
        "params_hash": acp_params_hash(params),
    }
