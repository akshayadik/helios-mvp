"""Research seed registry — single source of truth for all reproducibility seeds.

verify_osf_freeze.py --generate reads SEED_REGISTRY to produce seeds.json.
Any new seed requires a deviation log entry.
"""

from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

GLOBAL_SEED: int = 42
LLAMA_SEED: int = 42

HELIOS_ENABLE_RESEARCH_SEEDS: bool = True

SEED_REGISTRY: list[dict[str, str | int]] = [
    {
        "seed_id": "SEED-001",
        "value": GLOBAL_SEED,
        "stage": "Stage 0",
        "algorithm": "global",
        "context": "numpy.random.seed / random.seed",
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
]
