"""Ablation variants for confirmatory and exploratory evaluation phases.

Maps variant names to fixed VCLManifest instances — version-controlled so
any change to a variant definition is visible in git diff and requires a
deviation log entry if it has analytic consequence.

Derived from the approved Chapter 3 (owner decisions D1/D2, deviation
entries 24 and 31):
CONFIRMATORY_VARIANTS: the 8 variants of Table 17 (p.149-152).
EXPLORATORY_VARIANTS:  the 7 exploratory variants listed on p.153;
                       excluded from confirmatory analysis by evaluation_phase.

Conventions:
- Table 17 "passthru" (mechanism inactive because its upstream is absent) is OFF.
- Flags Table 17 does not name (fgsv_ks_gate, iol_self_telemetry,
  coe_narrative, his_tier, sampling_regime_tag) follow HELIOS-Full.
- Each exploratory variant is HELIOS-Full with exactly one flag OFF.
- Helpers live in catalog.py: this file is fingerprinted by the OSF freeze.
"""

from __future__ import annotations

from .config import VCLManifest

_FULL_FLAGS: dict[str, bool | str] = {
    "l2c_llm": True,
    "p4_cognitive": True,
    "mahc_hierarchical": True,
    "cbr_routing": True,
    "l2b_graph": True,
    "acp_stateful": True,
    "reconcile_terminal": True,
    "fgsv_ks_gate": True,
    "iol_self_telemetry": True,
    "coe_narrative": True,
    "his_tier": True,
    "sampling_regime_tag": True,
    "ueg_structural": True,
    "dpipe": True,
    "dpipe_propagation": True,
    "gpipe": True,
    "ingest_mode": "recorded",
}


def _full_except(**overrides: bool) -> VCLManifest:
    unknown = set(overrides) - set(_FULL_FLAGS)
    if unknown:
        raise ValueError(f"Unknown flags in variant definition: {sorted(unknown)}")
    return VCLManifest.from_flags(**{**_FULL_FLAGS, **overrides})


CONFIRMATORY_VARIANTS: dict[str, VCLManifest] = {
    # Reference: every mechanism on.
    "HELIOS-Full": _full_except(),
    # A-H1 (LLM necessity) and A-H7 (hallucination): L-pipe removed;
    # routing and consensus operate over D and G.
    "HELIOS-noLLM": _full_except(l2c_llm=False),
    # A-H2 (LLM sufficiency): L-pipe alone; consensus, routing, reconciliation passthru.
    "HELIOS-LLM-only": _full_except(
        mahc_hierarchical=False,
        cbr_routing=False,
        l2b_graph=False,
        acp_stateful=False,
        reconcile_terminal=False,
        dpipe=False,
        dpipe_propagation=False,
        gpipe=False,
    ),
    # A-H3 (statistical floor): D-pipe alone.
    "HELIOS-D": _full_except(
        l2c_llm=False,
        mahc_hierarchical=False,
        cbr_routing=False,
        l2b_graph=False,
        acp_stateful=False,
        reconcile_terminal=False,
        gpipe=False,
    ),
    # A-H4 (uncertainty-aware consensus value): MAHC replaced by vote-only fusion.
    "HELIOS-noConsensus": _full_except(mahc_hierarchical=False),
    # A-H5 (routing value): cost-based routing replaced by uniform routing.
    "HELIOS-noRouter": _full_except(cbr_routing=False),
    # A-H6 (graph-only on narrative-heavy incidents): G-pipe with the D-pipe trigger.
    "HELIOS-G": _full_except(
        l2c_llm=False,
        mahc_hierarchical=False,
        cbr_routing=False,
        acp_stateful=False,
        reconcile_terminal=False,
        dpipe_propagation=False,
    ),
    # A-H8 (C2 structural bundle): untyped edges, no subgraph-aware training,
    # Agent-Reasoning-Step nodes demoted to text.
    "HELIOS-noStructural": _full_except(ueg_structural=False),
}

EXPLORATORY_VARIANTS: dict[str, VCLManifest] = {
    "HELIOS-noCogni": _full_except(p4_cognitive=False),  # E-H1
    "HELIOS-noACP": _full_except(acp_stateful=False),  # E-H8 (E-H3 retired)
    "HELIOS-noReconcile": _full_except(reconcile_terminal=False),  # E-H5
    "HELIOS-HIS3": _full_except(his_tier=False),  # E-H9
    "HELIOS-noFGSV": _full_except(fgsv_ks_gate=False),  # E-H4
    "HELIOS-noIOL": _full_except(iol_self_telemetry=False),  # E-H6
    "HELIOS-noExpl": _full_except(coe_narrative=False),  # E-H7 (RQ4)
}


def get_variant(name: str) -> VCLManifest:
    """Resolve a variant name to its VCLManifest (confirmatory first, then exploratory)."""
    if name in CONFIRMATORY_VARIANTS:
        return CONFIRMATORY_VARIANTS[name]
    if name in EXPLORATORY_VARIANTS:
        return EXPLORATORY_VARIANTS[name]
    all_names = sorted({*CONFIRMATORY_VARIANTS, *EXPLORATORY_VARIANTS})
    raise ValueError(f"Unknown variant: {name!r}. Available: {all_names}")
