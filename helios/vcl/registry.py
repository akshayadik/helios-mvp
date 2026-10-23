"""VCL flag registry — single source of truth for all 17 feature flags.

Names follow the approved Chapter 3 (p.137-138, p.142; owner decision D2,
2026-10-23). Renamed from the May 2026 registry: mahc → mahc_hierarchical,
router + cbr → cbr_routing (Ch3's CBR is cost-based routing, ORAR),
acp → acp_stateful, reconcile → reconcile_terminal,
ueg_c_structural → ueg_structural; lpipe folded into l2c_llm.
"""

from __future__ import annotations

from enum import StrEnum


class VCLFlag(StrEnum):
    """All 17 VCL feature flags: 13 Chapter 3 flags, 3 implementation flags, ingest_mode.

    Adding a new flag requires only editing this enum (OCP).
    """

    # Chapter 3 flags (twelve named on p.137-138, plus ueg_structural, p.142)
    L2C_LLM = "l2c_llm"  # L-pipe (multi-agent LLM reasoning)
    P4_COGNITIVE = "p4_cognitive"  # cognitive-telemetry visibility to the L-pipe
    MAHC_HIERARCHICAL = "mahc_hierarchical"  # MAHC consensus; OFF = vote-only fusion
    CBR_ROUTING = "cbr_routing"  # cost-based router (ORAR); OFF = uniform routing
    L2B_GRAPH = "l2b_graph"  # UEG-C graph construction feeding the G-pipe
    ACP_STATEFUL = "acp_stateful"  # Action-Class Predictor; OFF = uniform prior
    RECONCILE_TERMINAL = "reconcile_terminal"  # two-stage reward reconciliation
    FGSV_KS_GATE = "fgsv_ks_gate"  # shadow validation behind the KS fidelity gate
    IOL_SELF_TELEMETRY = "iol_self_telemetry"  # HELIOS self-telemetry (tenant=self)
    COE_NARRATIVE = (
        "coe_narrative"  # Chain-of-Evidence narrative; OFF = ranked list only
    )
    HIS_TIER = "his_tier"  # design-committed hardware isolation; OFF = HIS-3
    SAMPLING_REGIME_TAG = (
        "sampling_regime_tag"  # tiered adaptive sampling + its covariate
    )
    UEG_STRUCTURAL = "ueg_structural"  # typed edges, subgraph-aware training, ARS nodes

    # Implementation flags kept by D2 (documented in the pre-registration)
    DPIPE = "dpipe"  # statistical pipeline entry point
    DPIPE_PROPAGATION = "dpipe_propagation"  # D-pipe graph propagation stage
    GPIPE = "gpipe"  # graph pipeline entry point

    # Operational extension — string value, not a boolean gate
    INGEST_MODE = "ingest_mode"

    @classmethod
    def all_flags(cls) -> list[str]:
        """All 17 flag values — for static audit and test_flag_count."""
        return [f.value for f in cls]

    @classmethod
    def bool_flags(cls) -> frozenset[VCLFlag]:
        """The 16 boolean flags safe for use with @gated_by.

        Excludes INGEST_MODE which carries a string value, not a bool.
        """
        return frozenset(f for f in cls if f is not cls.INGEST_MODE)
