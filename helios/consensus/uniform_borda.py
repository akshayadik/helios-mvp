"""UniformBorda consensus fusion and PassthroughConsensus fallback.

FUSION_CORE_VERSION is the stable identifier stored in every ConsensusVerdict.
FUSION_ALGORITHM_SHA is computed once at import from an AST fingerprint of this
module's source. Any change to the fusion logic will produce a different SHA —
the integrity gate catches drift between the stored SHA and the live computation.
"""

from __future__ import annotations

import ast
import datetime
import hashlib
import sys
from pathlib import Path
from typing import Any

from helios.consensus.verdict import CPR_PENDING, ConsensusVerdict
from helios.vcl import VCLFlag
from helios.vcl.decorators import gated_by

HELIOS_ENABLE_UNIFORM_BORDA: bool = True

__all__ = [
    "FUSION_ALGORITHM_SHA",
    "FUSION_CORE_VERSION",
    "PassthroughConsensus",
    "UniformBordaConsensus",
]

FUSION_CORE_VERSION: str = "borda-v1"


class _StripDocstrings(ast.NodeTransformer):
    def _strip(self, node: ast.AST) -> ast.AST:
        body = getattr(node, "body", [])
        if (
            len(body) > 1
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:]  # type: ignore[attr-defined]
        return node

    visit_FunctionDef = _strip  # noqa: N815
    visit_AsyncFunctionDef = _strip  # noqa: N815
    visit_ClassDef = _strip  # noqa: N815
    visit_Module = _strip  # noqa: N815


_REQUIRED_PYTHON_MINOR: tuple[int, int] = (3, 11)


def _compute_ast_hash() -> str:
    if sys.version_info[:2] != _REQUIRED_PYTHON_MINOR:
        raise RuntimeError(
            f"FUSION_ALGORITHM_SHA requires Python "
            f"{_REQUIRED_PYTHON_MINOR[0]}.{_REQUIRED_PYTHON_MINOR[1]}; "
            f"running {sys.version_info[:2]}. "
            "Re-activate the poetry environment: "
            "`poetry env use python3.11 && poetry install`."
        )
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    stripped = _StripDocstrings().visit(tree)
    ast.fix_missing_locations(stripped)
    return hashlib.sha256(ast.dump(stripped).encode()).hexdigest()


FUSION_ALGORITHM_SHA: str = _compute_ast_hash()


class UniformBordaConsensus:
    @gated_by(VCLFlag.MAHC)
    def fuse(
        self,
        *,
        incident_id: str,
        variant: str,
        pipeline_rows: list[dict[str, Any]],
        run_id: str,
    ) -> ConsensusVerdict:
        if not pipeline_rows:
            raise ValueError("pipeline_rows must be non-empty")

        all_candidates: set[str] = set()
        for row in pipeline_rows:
            all_candidates.update(row.get("ranked_candidates", []))

        n_candidates = len(all_candidates)
        scores: dict[str, float] = {c: float(0) for c in all_candidates}
        for row in pipeline_rows:
            ranked = row.get("ranked_candidates", [])
            for i, candidate in enumerate(ranked):
                if candidate in scores:
                    scores[candidate] += n_candidates - i - 1

        ordered = sorted(all_candidates, key=lambda c: (-scores[c], c))

        return ConsensusVerdict(
            incident_id=incident_id,
            variant=variant,
            top_candidates=ordered,
            borda_scores=scores,
            candidate_universe_size=n_candidates,
            consensus_rank=len(ordered),
            fusion_algorithm=FUSION_CORE_VERSION,
            fusion_algorithm_sha=FUSION_ALGORITHM_SHA,
            cpr=CPR_PENDING,
            pipeline_row_count=len(pipeline_rows),
            run_id=run_id,
            timestamp_utc=datetime.datetime.now(datetime.UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        )


_PASSTHROUGH_PIPELINE_PRIORITY: tuple[str, ...] = ("d_pipe", "g_pipe", "l_pipe")


class PassthroughConsensus:
    def fuse(
        self,
        *,
        incident_id: str,
        variant: str,
        pipeline_rows: list[dict[str, Any]],
        run_id: str,
    ) -> ConsensusVerdict:
        if not pipeline_rows:
            raise ValueError("pipeline_rows must be non-empty")

        priority_index = {p: i for i, p in enumerate(_PASSTHROUGH_PIPELINE_PRIORITY)}
        sorted_rows = sorted(
            pipeline_rows,
            key=lambda r: priority_index.get(
                r.get("pipeline", ""), len(_PASSTHROUGH_PIPELINE_PRIORITY)
            ),
        )
        top: list[str] = []
        all_scores: dict[str, float] = {}
        for row in sorted_rows:
            ranked = row.get("ranked_candidates", [])
            if ranked and not top:
                top = ranked
            for c in ranked:
                all_scores[c] = all_scores.get(c, 0)

        if not top:
            raise ValueError(
                f"No ranked candidates found in pipeline_rows for {incident_id}"
            )

        return ConsensusVerdict(
            incident_id=incident_id,
            variant=variant,
            top_candidates=top,
            borda_scores=all_scores,
            candidate_universe_size=len(all_scores),
            consensus_rank=len(top),
            fusion_algorithm="passthrough",
            fusion_algorithm_sha=FUSION_ALGORITHM_SHA,
            cpr=CPR_PENDING,
            pipeline_row_count=len(pipeline_rows),
            run_id=run_id,
            timestamp_utc=datetime.datetime.now(datetime.UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        )
