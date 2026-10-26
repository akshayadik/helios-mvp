"""Stage D: deterministic verdict — every scored service, ranked (S1.8: full list).

hr_at_3 / mrr are only filled when a calibration script passes ground truth;
the orchestrator never does, and they are not verdict fields (S1.9 scores
after dispatch).
"""

from __future__ import annotations

from typing import Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


class DVerdict:
    @staticmethod
    def compute(
        score_final: dict[str, float],
        ground_truth_service: str | None = None,
    ) -> dict[str, Any]:
        ranked = sorted(score_final, key=lambda s: (-score_final[s], s))
        hr_at_3 = 0
        mrr = float("nan")
        if ground_truth_service is not None:
            if ground_truth_service in ranked:
                gt_rank = ranked.index(ground_truth_service) + 1
            else:
                gt_rank = len(ranked) + 1
            hr_at_3 = int(ground_truth_service in ranked[:3])
            mrr = 1 / gt_rank
        return {
            "hr_at_3": hr_at_3,
            "mrr": mrr,
            "ranked_candidates": ranked,
            "narrative": None,
        }
