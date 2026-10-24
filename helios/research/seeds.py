"""Research seed registry — single source of truth for all reproducibility seeds.

verify_osf_freeze.py --generate reads SEED_REGISTRY and the register layout
(register_layout()) to produce seeds.json. Any new seed requires a deviation
log entry.

Binding seed register (Ch3 §3.3, p.108; S0.8, deviation entry 34): every seed
used by build, confirmatory or analysis work is one of the 10,000 integers
10,000,000-10,009,999. The register is cut into fixed blocks, one per purpose,
and a seed is pure arithmetic on frozen inputs (a slot name or an index into a
frozen ordering), so the same inputs give the same seed on any machine and two
confirmatory runs never share a seed. Slot tuples are append-only: a new slot
goes at the end, never in the middle, so existing seeds never move.

GLOBAL_SEED and LLAMA_SEED are the May 2026 values. They remain for the
exploratory OTel corpus and for L-pipe Protocol A (greedy decoding, where the
seed has no effect on the output); confirmatory work takes its seeds from the
register.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Sequence

GLOBAL_SEED: int = 42
LLAMA_SEED: int = 42

HELIOS_ENABLE_RESEARCH_SEEDS: bool = True

REGISTER_START: int = 10_000_000
REGISTER_SIZE: int = 10_000

# Run seeds: one per (case, system). Systems are the 15 variants and the
# 5 baselines, with 4 spare slots; up to 300 cases per corpus ordering.
RUN_SYSTEM_SLOTS: tuple[str, ...] = (
    # Confirmatory variants, Ch3 Table 17 order
    "HELIOS-Full",
    "HELIOS-noLLM",
    "HELIOS-LLM-only",
    "HELIOS-D",
    "HELIOS-noConsensus",
    "HELIOS-noRouter",
    "HELIOS-G",
    "HELIOS-noStructural",
    # Exploratory variants, Ch3 p.153 order
    "HELIOS-noCogni",
    "HELIOS-noACP",
    "HELIOS-noReconcile",
    "HELIOS-HIS3",
    "HELIOS-noFGSV",
    "HELIOS-noIOL",
    "HELIOS-noExpl",
    # Family B baselines, named before OSF deposit 1 (D5)
    "BASELINE-1",
    "BASELINE-2",
    "BASELINE-3",
    "BASELINE-4",
    "BASELINE-5",
)
_SYSTEMS_PER_CASE: int = 24
_MAX_CASES: int = 300

# Training seeds: one block of replicates per trained component. Replicate 0
# is the binding seed; replicates 1-5 are the robustness retrains (D11 §5).
TRAINING_SLOTS: tuple[str, ...] = (
    "gpipe_ranker",
    "acp_predictor",
    "mahc_confidence_calibration",
    "orar_prewarm_order",
)
_REPLICATES_PER_SLOT: int = 8
_MAX_TRAINING_SLOTS: int = 16

# BCa bootstrap seeds: one per hypothesis, in analysis-plan order.
BCA_HYPOTHESIS_SLOTS: tuple[str, ...] = (
    *(f"A-H{i}" for i in (3, 7, 1, 2, 6, 5, 4, 8)),
    *(f"B-H{i}" for i in (1, 2, 3, 4, 5, 7, 6, 8)),
    *(f"E-H{i}" for i in range(1, 11)),
)
_MAX_BCA_SLOTS: int = 64

# Opaque incident-ID generation: one seed per corpus (D11 §3, F1).
OPAQUE_ID_CORPUS_SLOTS: tuple[str, ...] = (
    "rcaeval_confirmatory",
    "rcaeval_build",
    "otel_exploratory",
)
_MAX_OPAQUE_ID_SLOTS: int = 16

# ORAR / ACP pre-warm sequence on the synthetic corpus (Ch3: 1,200 incidents).
PREWARM_LENGTH: int = 1_200

# (purpose, first offset, size). Offsets are relative to REGISTER_START;
# 8,608-9,999 is reserved for later purposes (one new block per deviation).
_BLOCKS: tuple[tuple[str, int, int], ...] = (
    ("run", 0, _SYSTEMS_PER_CASE * _MAX_CASES),
    ("training", 7_200, _REPLICATES_PER_SLOT * _MAX_TRAINING_SLOTS),
    ("bca", 7_328, _MAX_BCA_SLOTS),
    ("opaque_id", 7_392, _MAX_OPAQUE_ID_SLOTS),
    ("prewarm", 7_408, PREWARM_LENGTH),
)
_BLOCK_BY_PURPOSE: dict[str, tuple[int, int]] = {
    name: (first, size) for name, first, size in _BLOCKS
}


def seed_for(purpose: str, index: int) -> int:
    """Seed at position ``index`` of the block for ``purpose``."""
    if purpose not in _BLOCK_BY_PURPOSE:
        raise ValueError(f"unknown seed purpose {purpose!r}")
    first, size = _BLOCK_BY_PURPOSE[purpose]
    if not 0 <= index < size:
        raise ValueError(f"{purpose} index {index} outside [0, {size})")
    return REGISTER_START + first + index


def _slot(slots: Sequence[str], name: str, kind: str) -> int:
    if name not in slots:
        raise ValueError(f"unregistered {kind} {name!r}")
    return slots.index(name)


def run_seed(case_id: str, system: str, *, case_order: Sequence[str]) -> int:
    """Seed for one run of ``system`` on ``case_id``.

    ``case_order`` is the frozen case ordering recorded in the sealed corpus
    manifest; a case's position in it, not its name, picks the seed.
    """
    if len(set(case_order)) != len(case_order):
        raise ValueError("case_order contains duplicate case IDs")
    if case_id not in case_order:
        raise ValueError(f"case {case_id!r} not in case_order")
    case_index = list(case_order).index(case_id)
    system_index = _slot(RUN_SYSTEM_SLOTS, system, "system")
    return seed_for("run", case_index * _SYSTEMS_PER_CASE + system_index)


def training_seed(component: str, replicate: int = 0) -> int:
    """Seed for training ``component``; replicate 0 is binding, 1-5 robustness."""
    if not 0 <= replicate < _REPLICATES_PER_SLOT:
        raise ValueError(f"replicate {replicate} outside [0, {_REPLICATES_PER_SLOT})")
    slot = _slot(TRAINING_SLOTS, component, "training component")
    return seed_for("training", slot * _REPLICATES_PER_SLOT + replicate)


def bca_seed(hypothesis_id: str) -> int:
    """Seed for the BCa bootstrap of one hypothesis."""
    return seed_for("bca", _slot(BCA_HYPOTHESIS_SLOTS, hypothesis_id, "hypothesis"))


def opaque_id_seed(corpus: str) -> int:
    """Seed for generating the opaque incident IDs of one corpus."""
    return seed_for(
        "opaque_id", _slot(OPAQUE_ID_CORPUS_SLOTS, corpus, "opaque-ID corpus")
    )


def prewarm_seed(position: int) -> int:
    """Seed for incident ``position`` of the pre-warm sequence."""
    return seed_for("prewarm", position)


def register_layout() -> dict[str, object]:
    """The frozen layout, as written to research/osf/seeds.json."""
    layout: dict[str, object] = {
        "first_seed": REGISTER_START,
        "last_seed": REGISTER_START + REGISTER_SIZE - 1,
        "blocks": [
            {
                "purpose": name,
                "first_seed": REGISTER_START + first,
                "last_seed": REGISTER_START + first + size - 1,
            }
            for name, first, size in _BLOCKS
        ],
        "run_seed_rule": (
            "first_seed(run) + case_index * "
            f"{_SYSTEMS_PER_CASE} + system_index; case_index from the sealed "
            "corpus manifest case order"
        ),
        "run_system_slots": list(RUN_SYSTEM_SLOTS),
        "training_seed_rule": (
            f"first_seed(training) + slot * {_REPLICATES_PER_SLOT} + replicate; "
            "replicate 0 binding, 1-5 robustness retrains"
        ),
        "training_slots": list(TRAINING_SLOTS),
        "bca_hypothesis_slots": list(BCA_HYPOTHESIS_SLOTS),
        "opaque_id_corpus_slots": list(OPAQUE_ID_CORPUS_SLOTS),
        "prewarm_length": PREWARM_LENGTH,
    }
    digest = hashlib.sha256(
        json.dumps(layout, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {**layout, "layout_sha256": digest}


SEED_REGISTRY: list[dict[str, str | int]] = [
    {
        "seed_id": "SEED-001",
        "value": GLOBAL_SEED,
        "stage": "Stage 0",
        "algorithm": "global",
        "context": "numpy.random.seed / random.seed (exploratory OTel corpus only)",
        "source_constant": "helios.research.seeds.GLOBAL_SEED",
    },
    {
        "seed_id": "SEED-002",
        "value": LLAMA_SEED,
        "stage": "Stage 1",
        "algorithm": "llama3.1:8b inference",
        "context": "Ollama Protocol A seed",
        "source_constant": "helios.pipelines.l_pipe.lpipe_config.LLAMA_SEED",
    },
    {
        "seed_id": "SEED-003",
        "value": REGISTER_START,
        "stage": "Stage A / S0",
        "algorithm": "binding seed register (first seed; layout in 'register')",
        "context": "confirmatory runs, training, BCa, opaque IDs, pre-warm",
        "source_constant": "helios.research.seeds.REGISTER_START",
    },
]
