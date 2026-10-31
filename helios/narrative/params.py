"""Narrator parameters frozen with the prompt (S2.8 design §5.8)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json

__all__ = [
    "NARRATOR_PARAMS_PATH",
    "NarratorParams",
    "load_narrator_params",
    "narrator_params_hash",
]

NARRATOR_PARAMS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "frozen" / "narrator_params.json"
)


@dataclass(frozen=True)
class NarratorParams:
    """Direction words, read-only verbs and the numeric tolerance."""

    direction_words: dict[str, tuple[str, ...]]
    verbs: tuple[str, ...]
    rel_tolerance: float
    max_steps: int
    provisional: bool
    # Closed vocabulary (owner decision N-j): the words a sentence of each kind
    # may use besides its own service names, numbers and units.
    vocabulary: dict[str, tuple[str, ...]]
    channel_words: dict[str, tuple[str, ...]]
    rank_words: dict[str, int]
    pipeline_words: dict[str, str]
    max_words: int
    min_snippet_chars: int


def load_narrator_params(path: Path = NARRATOR_PARAMS_PATH) -> NarratorParams:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return NarratorParams(
        direction_words={k: tuple(v) for k, v in raw["direction_words"].items()},
        verbs=tuple(raw["verbs"]),
        rel_tolerance=float(raw["rel_tolerance"]),
        max_steps=int(raw["max_steps"]),
        provisional=bool(raw["provisional"]),
        vocabulary={k: tuple(v) for k, v in raw["vocabulary"].items()},
        channel_words={k: tuple(v) for k, v in raw["channel_words"].items()},
        rank_words={k: int(v) for k, v in raw["rank_words"].items()},
        pipeline_words=dict(raw["pipeline_words"]),
        max_words=int(raw["max_words"]),
        min_snippet_chars=int(raw["min_snippet_chars"]),
    )


def narrator_params_hash(params: NarratorParams) -> str:
    """SHA-256 of the canonical parameters (frozen with the prompt, entry C)."""
    raw = asdict(params)
    raw["verbs"] = list(params.verbs)
    raw["direction_words"] = {k: list(v) for k, v in params.direction_words.items()}
    raw["vocabulary"] = {k: list(v) for k, v in params.vocabulary.items()}
    raw["channel_words"] = {k: list(v) for k, v in params.channel_words.items()}
    payload = canonical_json(raw).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
