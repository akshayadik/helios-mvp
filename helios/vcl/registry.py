"""VCL flag registry — single source of truth for all 14 feature flags."""

from __future__ import annotations

from enum import StrEnum


class VCLFlag(StrEnum):
    """All 14 VCL feature flags (12 proposal §3.6.7 + router + ingest_mode).

    Adding a new flag requires only editing this enum (OCP).
    """

    # 12 proposal flags (Table 12 / §3.6.7)
    L2C_LLM = "l2c_llm"
    P4_COGNITIVE = "p4_cognitive"
    MAHC = "mahc"
    CBR = "cbr"
    L2B_GRAPH = "l2b_graph"
    ACP = "acp"
    RECONCILE = "reconcile"
    UEG_C_STRUCTURAL = "ueg_c_structural"
    DPIPE = "dpipe"
    DPIPE_PROPAGATION = "dpipe_propagation"
    GPIPE = "gpipe"
    LPIPE = "lpipe"

    # Cross-pipeline routing (boolean gate)
    ROUTER = "router"

    # Operational extension — string value, not a boolean gate
    INGEST_MODE = "ingest_mode"

    @classmethod
    def all_flags(cls) -> list[str]:
        """All 14 flag values — for static audit and test_flag_count."""
        return [f.value for f in cls]

    @classmethod
    def bool_flags(cls) -> frozenset[VCLFlag]:
        """The 13 boolean flags safe for use with @gated_by.

        Excludes INGEST_MODE which carries a string value, not a bool.
        """
        return frozenset(f for f in cls if f is not cls.INGEST_MODE)
