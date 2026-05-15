"""CorpusLoader — resolve a corpus path to an ordered sequence of incident IDs.

Accepts a directory (discovers sub-dirs containing manifest.json) or a JSON file
with {"incidents": [...]} list. Used by RunOrchestrator to iterate the corpus
without knowing its on-disk format.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["CorpusLoader"]

HELIOS_ENABLE_ORCHESTRATOR: bool = True


class CorpusLoader:
    """Yield incident IDs from a directory or a JSON corpus manifest."""

    def __init__(self, corpus: Path) -> None:
        self._corpus = corpus

    def incident_ids(self) -> Iterator[str]:
        """Yield incident IDs in deterministic order."""
        if self._corpus.is_dir():
            yield from self._from_directory()
        elif self._corpus.suffix == ".json":
            yield from self._from_json()
        else:
            raise ValueError(
                f"Cannot load corpus from {self._corpus!r}. "
                'Pass a directory or a .json file with {"incidents": [...]}'
            )

    def _from_directory(self) -> Iterator[str]:
        for child in sorted(self._corpus.iterdir()):
            if child.is_dir() and (child / "manifest.json").exists():
                yield child.name

    def _from_json(self) -> Iterator[str]:
        data: dict[str, object] = json.loads(self._corpus.read_text(encoding="utf-8"))
        if "incidents" not in data:
            raise ValueError(
                f"Corpus JSON must have an 'incidents' key: {self._corpus}"
            )
        incidents = data["incidents"]
        if not isinstance(incidents, list):
            raise ValueError(
                f"'incidents' must be a list, got {type(incidents).__name__}: {self._corpus}"
            )
        for item in incidents:
            if not isinstance(item, str):
                raise ValueError(
                    f"All incidents must be strings, got {type(item).__name__}: {item!r}"
                )
            yield item
