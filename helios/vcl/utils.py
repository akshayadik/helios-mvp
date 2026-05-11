"""Canonical JSON serialiser for VCL hash stability."""

from __future__ import annotations

import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, 6-decimal floats, UTF-8.

    Floats are pre-normalised (round-to-6) before serialisation because
    json.dumps handles floats natively and never calls the `default` hook.
    Raises TypeError for non-serialisable types.
    """

    def _normalise(o: Any) -> Any:
        if isinstance(o, bool):  # bool subclasses int — check first
            return o
        if isinstance(o, float):
            return round(o, 6)
        if isinstance(o, int | str | type(None)):
            return o
        if isinstance(o, dict):
            return {k: _normalise(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_normalise(item) for item in o]
        raise TypeError(f"Object of type {type(o).__name__!r} is not JSON serialisable")

    return json.dumps(
        _normalise(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
