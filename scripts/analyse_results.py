#!/usr/bin/env python3
"""Exploratory statistical analysis: Wilcoxon + Holm-Bonferroni over A-family hypotheses.

Results are exploratory (OTEL corpus). They do not constitute binding inference.
Phase 2 (AIOpsLab) provides the confirmatory test.

Usage:
    python scripts/analyse_results.py --db-path /tmp/helios-m4/helios_m4_results.duckdb
    python scripts/analyse_results.py --db-path /tmp/... --output data/m4_results.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

from helios.vcl.config import VCLManifest  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_ANALYSE_RESULTS: bool = True

EXPLORATORY_ALPHA: float = 0.05


def run_wilcoxon(
    scores_a: list[float],
    scores_b: list[float],
) -> dict[str, Any]:
    from scipy.stats import wilcoxon

    from helios.config.m4_ablation import MIN_WILCOXON_PAIRS

    if len(scores_a) < MIN_WILCOXON_PAIRS:
        return {
            "pvalue": float("nan"),
            "statistic": float("nan"),
            "effect_r": float("nan"),
            "n_nonzero": 0,
            "zero_variance": False,
            "insufficient_sample": True,
            "n_pairs": len(scores_a),
        }

    diffs = np.array(scores_a) - np.array(scores_b)
    nonzero_diffs = diffs[np.abs(diffs) > 0]
    n_nonzero = int(len(nonzero_diffs))

    if n_nonzero == 0:
        return {
            "pvalue": float("nan"),
            "statistic": float("nan"),
            "effect_r": float("nan"),
            "n_nonzero": n_nonzero,
            "zero_variance": True,
            "insufficient_sample": False,
            "n_pairs": len(scores_a),
        }

    try:
        stat, pvalue = wilcoxon(diffs, alternative="two-sided", method="exact")
    except ValueError:
        return {
            "pvalue": float("nan"),
            "statistic": float("nan"),
            "effect_r": float("nan"),
            "n_nonzero": n_nonzero,
            "zero_variance": True,
            "insufficient_sample": False,
            "n_pairs": len(scores_a),
        }

    denom = n_nonzero * (n_nonzero + 1) / 2
    effect_r = float(1 - (2 * stat) / denom) if denom > 0 else float("nan")

    return {
        "pvalue": float(pvalue),
        "statistic": float(stat),
        "effect_r": effect_r,
        "n_nonzero": n_nonzero,
        "zero_variance": False,
        "insufficient_sample": False,
        "n_pairs": len(scores_a),
    }


def apply_holm_bonferroni(
    pvalues: dict[str, float],
) -> dict[str, dict[str, Any]]:
    from statsmodels.stats.multitest import multipletests

    hyp_ids = list(pvalues.keys())
    raw = [pvalues[h] for h in hyp_ids]

    valid_idx = [i for i, p in enumerate(raw) if not math.isnan(p)]
    valid_raw = [raw[i] for i in valid_idx]

    corrected_map: dict[int, tuple[bool, float]] = {}
    if valid_raw:
        rejected, corrected, _, _ = multipletests(
            valid_raw, method="holm", alpha=EXPLORATORY_ALPHA
        )
        for j, i in enumerate(valid_idx):
            corrected_map[i] = (bool(rejected[j]), float(corrected[j]))

    result: dict[str, dict[str, Any]] = {}
    for i, hyp_id in enumerate(hyp_ids):
        if i in corrected_map:
            rej, corr_p = corrected_map[i]
            result[hyp_id] = {
                "raw_pvalue": raw[i],
                "corrected_pvalue": corr_p,
                "rejected": rej,
                "zero_variance": False,
            }
        else:
            result[hyp_id] = {
                "raw_pvalue": raw[i],
                "corrected_pvalue": float("nan"),
                "rejected": False,
                "zero_variance": True,
            }
    return result


def _load_consensus_hr_at_3_pairs(
    db_path: Path,
    ground_truth_path: Path,
    variant_a: str,
    variant_b: str,
) -> tuple[list[float], list[float]]:
    """Load system-level (consensus) HR@3 pairs for variant_a vs variant_b.

    Queries consensus_verdict.top_candidates — the fused system output — and
    computes HR@3 against ground truth.  Single-pipeline slices ignore the
    peer pipelines and do not reflect multi-pipeline system output.
    """
    import duckdb

    from helios.config.m4_ablation import MIN_WILCOXON_PAIRS
    from helios.evaluation.metrics import hr_at_k

    ground_truth: dict[str, str] = json.loads(
        ground_truth_path.read_text(encoding="utf-8")
    )

    conn = duckdb.connect(str(db_path), read_only=True)
    rows_a = conn.execute(
        "SELECT incident_id, top_candidates FROM consensus_verdict WHERE variant = ?",
        [variant_a],
    ).fetchall()
    rows_b = conn.execute(
        "SELECT incident_id, top_candidates FROM consensus_verdict WHERE variant = ?",
        [variant_b],
    ).fetchall()
    conn.close()

    def _to_hr(rows: list[tuple[Any, ...]]) -> dict[str, float]:
        hr_map: dict[str, float] = {}
        for incident_id, top_json in rows:
            if incident_id not in ground_truth:
                continue
            ranked: list[str] = (
                json.loads(top_json) if isinstance(top_json, str) else list(top_json)
            )
            hr_map[incident_id] = float(hr_at_k(ranked, ground_truth[incident_id], k=3))
        return hr_map

    a_map = _to_hr(rows_a)
    b_map = _to_hr(rows_b)
    common = sorted(set(a_map) & set(b_map))

    if len(common) < MIN_WILCOXON_PAIRS:
        print(
            f"WARNING: only {len(common)} paired incidents for "
            f"{variant_a} vs {variant_b}; "
            f"skipping Wilcoxon (floor={MIN_WILCOXON_PAIRS})",
            file=sys.stderr,
        )
        return [], []

    return [a_map[k] for k in common], [b_map[k] for k in common]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exploratory statistical analysis.")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument(
        "--ground-truth-path",
        type=Path,
        default=Path("data/ground_truth.json"),
        help="JSON map of {incident_id: root_cause_service}",
    )
    parser.add_argument("--output", type=Path, default=Path("data/m4_results.json"))
    args = parser.parse_args(argv)

    if not args.db_path.exists():
        print(f"ERROR: DB not found: {args.db_path}", file=sys.stderr)
        return 1

    if not args.ground_truth_path.exists():
        print(
            f"ERROR: ground truth not found: {args.ground_truth_path}", file=sys.stderr
        )
        print("  Run: python scripts/compile_ground_truth.py", file=sys.stderr)
        return 1

    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES

    raw_pvalues: dict[str, float] = {}
    per_hyp: dict[str, Any] = {}

    for hyp in FAMILY_A_HYPOTHESES:
        hyp_id = str(hyp["id"])
        comparison = str(hyp["comparison"])
        parts = [p.strip() for p in comparison.split(" vs ")]
        if len(parts) != 2:
            continue
        variant_a, variant_b = parts[0], parts[1].split(" ")[0]

        try:
            scores_a, scores_b = _load_consensus_hr_at_3_pairs(
                args.db_path,
                args.ground_truth_path,
                variant_a,
                variant_b,
            )
        except Exception as exc:
            print(f"  Skipping {hyp_id}: {exc}")
            raw_pvalues[hyp_id] = float("nan")
            per_hyp[hyp_id] = {"skipped": True, "reason": str(exc)}
            continue

        wstat = run_wilcoxon(scores_a, scores_b)
        raw_pvalues[hyp_id] = wstat["pvalue"]
        per_hyp[hyp_id] = {**wstat, "comparison": comparison, "n_pairs": len(scores_a)}

    corrected = apply_holm_bonferroni(raw_pvalues)
    for hyp_id, corr in corrected.items():
        per_hyp.setdefault(hyp_id, {}).update(corr)

    output: dict[str, Any] = {
        "corpus": "otel-demo",
        "analysis_type": "exploratory",
        "note": "OTEL results are exploratory only; no binding inference",
        "hypotheses": per_hyp,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Results written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
