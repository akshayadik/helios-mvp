"""Confirmatory ablation variants from Table 12 (§3.6.7).

Maps variant names to fixed VCLManifest instances — version-controlled so
any change to a variant definition is visible in git diff and requires a
deviation log entry if it has analytic consequence.
"""

from __future__ import annotations

from .config import VCLManifest

# All variants share ingest_mode="recorded" (primary evaluation protocol).
# router=True is the VCLManifest default; only HELIOS-noRouter overrides it.
CONFIRMATORY_VARIANTS: dict[str, VCLManifest] = {
    "HELIOS-Full": VCLManifest.from_flags(
        l2c_llm=True,
        p4_cognitive=True,
        mahc=True,
        cbr=True,
        l2b_graph=True,
        acp=True,
        reconcile=True,
        ueg_c_structural=True,
        dpipe=True,
        dpipe_propagation=True,
        gpipe=True,
        lpipe=True,
        router=True,
        ingest_mode="recorded",
    ),
    "HELIOS-noLLM": VCLManifest.from_flags(
        l2c_llm=False,
        p4_cognitive=True,
        mahc=True,
        cbr=True,
        l2b_graph=True,
        acp=True,
        reconcile=True,
        ueg_c_structural=True,
        dpipe=True,
        dpipe_propagation=True,
        gpipe=True,
        lpipe=False,
        router=True,
        ingest_mode="recorded",
    ),
    "HELIOS-noGraph": VCLManifest.from_flags(
        l2c_llm=True,
        p4_cognitive=True,
        mahc=True,
        cbr=True,
        l2b_graph=False,
        acp=True,
        reconcile=True,
        ueg_c_structural=True,
        dpipe=True,
        dpipe_propagation=True,
        gpipe=False,
        lpipe=True,
        router=True,
        ingest_mode="recorded",
    ),
    "HELIOS-D": VCLManifest.from_flags(
        l2c_llm=False,
        p4_cognitive=True,
        mahc=False,
        cbr=False,
        l2b_graph=False,
        acp=False,
        reconcile=False,
        ueg_c_structural=True,
        dpipe=True,
        dpipe_propagation=True,
        gpipe=False,
        lpipe=False,
        router=False,
        ingest_mode="recorded",
    ),
    "HELIOS-G": VCLManifest.from_flags(
        l2c_llm=False,
        p4_cognitive=True,
        mahc=False,
        cbr=False,
        l2b_graph=True,
        acp=False,
        reconcile=False,
        ueg_c_structural=True,
        dpipe=True,
        dpipe_propagation=False,
        gpipe=True,
        lpipe=False,
        router=False,
        ingest_mode="recorded",
    ),
    "HELIOS-noConsensus": VCLManifest.from_flags(
        l2c_llm=True,
        p4_cognitive=True,
        mahc=False,
        cbr=True,
        l2b_graph=True,
        acp=True,
        reconcile=True,
        ueg_c_structural=True,
        dpipe=True,
        dpipe_propagation=True,
        gpipe=True,
        lpipe=True,
        router=True,
        ingest_mode="recorded",
    ),
    "HELIOS-noRouter": VCLManifest.from_flags(
        l2c_llm=True,
        p4_cognitive=True,
        mahc=True,
        cbr=True,
        l2b_graph=True,
        acp=True,
        reconcile=True,
        ueg_c_structural=True,
        dpipe=True,
        dpipe_propagation=True,
        gpipe=True,
        lpipe=True,
        router=False,
        ingest_mode="recorded",
    ),
    "HELIOS-noStructural": VCLManifest.from_flags(
        l2c_llm=True,
        p4_cognitive=True,
        mahc=True,
        cbr=True,
        l2b_graph=True,
        acp=True,
        reconcile=True,
        ueg_c_structural=False,
        dpipe=True,
        dpipe_propagation=True,
        gpipe=True,
        lpipe=True,
        router=True,
        ingest_mode="recorded",
    ),
}


def get_variant(name: str) -> VCLManifest:
    """Resolve a variant name to its fixed VCLManifest (used by orchestrator)."""
    if name not in CONFIRMATORY_VARIANTS:
        raise ValueError(
            f"Unknown variant: {name!r}. " f"Available: {sorted(CONFIRMATORY_VARIANTS)}"
        )
    return CONFIRMATORY_VARIANTS[name]
