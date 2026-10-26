"""Stage D: deterministic verdict — every scored service, ranked.

Score-descending, ties by name. Stage D never sees ground truth: accuracy is
scored after dispatch by helios/evaluation/scoring.py (S1.9).
"""

from __future__ import annotations

from typing import Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


class DVerdict:
    @staticmethod
    def compute(score_final: dict[str, float]) -> dict[str, Any]:
        ranked = sorted(score_final, key=lambda s: (-score_final[s], s))
        return {"ranked_candidates": ranked, "narrative": None}
