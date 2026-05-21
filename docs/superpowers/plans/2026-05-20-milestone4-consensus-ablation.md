# Milestone 4: Consensus + Ablation Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement UniformBorda consensus, execute the 480-row OTEL exploratory ablation matrix (20 incidents × 8 variants × 3 pipelines), compute exploratory Wilcoxon statistics with Holm-Bonferroni correction, and produce C1 evidence artefacts for Milestone 4 exit.

**Architecture:** Subprocess-isolated per-variant runs produce per-variant DuckDB files that are atomically merged into a single central DB; `fuse_verdicts.py` applies `UniformBordaConsensus` to each incident's pipeline rows, writing `ConsensusVerdict` rows; `analyse_results.py` loads those rows, runs Wilcoxon exact two-sided per A-family hypothesis, and emits a Holm-Bonferroni-corrected results table. No frozen interfaces (`RunOrchestrator`, `PipelineVerdict` schema-draft-v0.2) are modified.

**Tech Stack:** Python 3.11, DuckDB 0.10+, Pydantic v2, scipy (Wilcoxon), statsmodels (Holm-Bonferroni), hypothesis (property testing), poetry, pytest, ruff/mypy strict

---

## File Map

### New files

| Path | Purpose |
|---|---|
| `helios/config/__init__.py` | Package marker |
| `helios/config/m4_ablation.py` | Frozen M4 numeric constants |
| `helios/evaluation/__init__.py` | Package marker |
| `helios/evaluation/metrics.py` | `hr_at_k()` hit-rate metric |
| `helios/consensus/__init__.py` | Re-exports public consensus API |
| `helios/consensus/verdict.py` | `ConsensusVerdict` schema + `ConsensusIntegrityGate` |
| `helios/consensus/uniform_borda.py` | `UniformBordaConsensus`, `PassthroughConsensus`, `_compute_ast_hash()` |
| `scripts/compile_ground_truth.py` | Parses `ground_truth_labelling.md` → `data/ground_truth.json` |
| `scripts/run_one_variant.py` | Subprocess entry: instantiates `RunOrchestrator` for one named variant |
| `scripts/run_ablation.py` | Loops all 8 variants via subprocess, atomic merge, smoke check |
| `scripts/fuse_verdicts.py` | Idempotent fusion: applies Borda per incident, writes `ConsensusVerdict` rows |
| `scripts/analyse_results.py` | Wilcoxon + Holm-Bonferroni over pre-registered A-family hypotheses |
| `scripts/replicate.py` | 10-percent byte-equality replication check (2 incidents) |
| `docs/reproducibility/m4_replication.md` | Replication log template |
| `tests/test_m4_ablation_config.py` | Tests for M4 constants |
| `tests/test_metrics.py` | Tests for `hr_at_k` |
| `tests/test_compile_ground_truth.py` | Tests for ground truth compiler |
| `tests/consensus/__init__.py` | Package marker |
| `tests/consensus/test_consensus_verdict.py` | Schema validation tests |
| `tests/consensus/test_uniform_borda.py` | Unit tests for Borda + Passthrough |
| `tests/consensus/test_uniform_borda_property.py` | Hypothesis property tests |
| `tests/integration/__init__.py` | Package marker |
| `tests/integration/test_run_ablation_dry_run.py` | Integration test for `--dry-run` path |

### Modified files

| Path | Change |
|---|---|
| `pyproject.toml` | Add `statsmodels = ">=0.14"`, `hypothesis = "^6"` |
| `helios/vcl/variants.py` | Add `get_all_variants()` |
| `helios/vcl/__init__.py` | Export `get_all_variants` |
| `helios/store/schema.sql` | Add `consensus_verdict` table; bump tag to `schema-draft-v0.3` |
| `helios/store/result_store.py` | Add `insert_consensus()`, `fetch_all_pipeline_rows()`, `fetch_all_consensus_rows()` |
| `helios/orchestrator/ledger.py` | Add `consensus_computed`, `consensus_skipped`, `consensus_excluded` to OUTCOMES |
| `docs/tracking/helios_mvp_tracking.md` | M4 task rows |
| `docs/tracking/ablation_architecture.md` | §5 Consensus layer |

---

### Task 1: Pre-implementation gate — docs, dependencies, deviation entries

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/tracking/helios_mvp_tracking.md`
- Modify: `docs/tracking/ablation_architecture.md`

- [ ] **Step 1: Add missing dependencies to pyproject.toml**

In the `[tool.poetry.dependencies]` section of `pyproject.toml`, add:

```toml
statsmodels = ">=0.14"
hypothesis = "^6"
```

- [ ] **Step 2: Regenerate lock file and verify imports**

```bash
set -a; source .env; set +a
poetry lock
poetry install
poetry run python -c "import statsmodels; import hypothesis; print('deps ok')"
```

Expected output: `deps ok`. If `poetry lock` errors, check that no other dependency conflicts exist.

- [ ] **Step 3: Add M4 tracking rows to helios_mvp_tracking.md**

In `docs/tracking/helios_mvp_tracking.md`, add a `## Milestone 4` section with these PLANNED rows (use exactly the column schema from existing rows; immutable columns: Task_ID, Day, Type, Description, Prop, DSR, Contrib, Owner, Deps):

```
| S1-M4-ENG01 | 1 | ENG | Add consensus module: ConsensusVerdict, UniformBorda, schema-draft-v0.3 | §3.6.9 | G3-C | C3,C5 | Akshay | M3-complete | | PLANNED | | | | | |
| S1-M4-ENG02 | 2 | ENG | Ablation runner: run_one_variant.py, run_ablation.py, fuse_verdicts.py | §3.7 | G3-D | C1,C6 | Akshay | S1-M4-ENG01 | | PLANNED | | | | | |
| S1-M4-ENG03 | 3 | ENG | Statistical analysis: analyse_results.py, Wilcoxon, Holm-Bonferroni | §4.3 | G4-A | C5 | Akshay | S1-M4-ENG02 | | PLANNED | | | | | |
| S1-M4-RES01 | 4 | RES | Execute ablation matrix: 20 incidents × 8 variants (480 pipeline rows) | §3.7 | G3-D | — | Akshay | S1-M4-ENG02 | | PLANNED | | | | | |
| S1-M4-RES02 | 5 | RES | Exploratory Wilcoxon run + C1 evidence tables | §4.3 | G4-B | — | Akshay | S1-M4-ENG03,S1-M4-RES01 | | PLANNED | | | | | |
| S1-M4-EVAL01 | 5 | EVAL | Extend ablation_notebook.ipynb L4 section | §5.2 | G5-A | — | Akshay | S1-M4-RES02 | | PLANNED | | | | | |
| S1-M4-GATE01 | 5 | GATE | M4 exit gate: all criteria met, pre-push gate passes | §6 | G5-B | — | Akshay | S1-M4-EVAL01 | | PLANNED | | | | | |
```

- [ ] **Step 4: Log deviation entry — consensus module introduction**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M4" \
  --clause "§3.6.9 Consensus layer" \
  --change "Introduce helios/consensus/: UniformBordaConsensus, ConsensusVerdict, schema-draft-v0.3 table" \
  --reason "Milestone 4 requires consensus fusion layer not present in M3 freeze" \
  --analytic-consequence "Adds consensus_verdict DuckDB table; PipelineVerdict schema-draft-v0.2 is unchanged"
```

- [ ] **Step 5: Log deviation entry — ablation runner**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M4" \
  --clause "§3.7 Exploratory run protocol" \
  --change "Introduce scripts/run_ablation.py: subprocess-isolated per-variant runs, atomic merge of 8 per-variant DuckDB files" \
  --reason "480-row ablation matrix requires multi-variant orchestration beyond RunOrchestrator scope" \
  --analytic-consequence "None — RunOrchestrator is frozen; subprocess isolation preserves per-variant DB lineage"
```

- [ ] **Step 6: Log deviation entry — statistical analysis addition**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M4" \
  --clause "§4.3 Exploratory inference" \
  --change "Introduce scripts/analyse_results.py: Wilcoxon exact two-sided + Holm-Bonferroni over pre-registered A-family hypotheses" \
  --reason "Pre-registered analysis plan requires exploratory statistical pass before confirmatory runs" \
  --analytic-consequence "Exploratory only (OTEL corpus); no binding inference; informs Phase 2 planning"
```

- [ ] **Step 7: Verify deviation chain**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py verify
poetry run pytest tests/test_deviation_log.py -v
```

Expected: `Chain is valid` and all deviation log tests pass.

- [ ] **Step 8: Append §5 to ablation_architecture.md**

Append the following section to `docs/tracking/ablation_architecture.md`:

```markdown
## §5 Consensus Layer (Milestone 4)

**Decision:** `UniformBordaConsensus` is the sole fusion algorithm for the OTEL exploratory run.
The `fusion_algorithm` field in `ConsensusVerdict` is an immutable tamper-anchor; any post-freeze
change requires a deviation log entry.

**Variants and passthrough:** Variants with the consensus flag disabled (e.g., `HELIOS-noConsensus`)
route through `PassthroughConsensus`, which propagates the top-ranked `PipelineVerdict` directly.
The `ConsensusVerdict.fusion_algorithm` is set to `"passthrough"` in this case.

**AST fingerprint:** `FUSION_ALGORITHM_SHA` is computed at module import via `ast.dump(ast.parse(source))`
with docstrings stripped. It is stored in every `ConsensusVerdict` row and verified by
`ConsensusIntegrityGate` before any row is written.

**Schema version:** `schema-draft-v0.3` adds the `consensus_verdict` table.
`result_row` (schema-draft-v0.2) is unchanged; the two schemas coexist in the same DuckDB file.

**Two-environment firewall:** All M4 runs use the OTEL Demo corpus (exploratory).
AIOpsLab corpus runs (confirmatory, Phase 2) must never share a DuckDB file with OTEL results.
```

- [ ] **Step 9: Run full test suite to verify gate is clean before any new code**

```bash
set -a; source .env; set +a
poetry run pytest --tb=short
make validate-tracking
```

Expected: all existing tests pass; tracking schema valid.

- [ ] **Step 10: Commit gate**

```bash
git add pyproject.toml poetry.lock docs/tracking/helios_mvp_tracking.md \
    docs/tracking/ablation_architecture.md deviation_log.jsonl
git commit -m "docs(m4): pre-implementation gate — deps, tracking rows, 3 deviation entries, §5 arch"
```

---

### Task 2: VCL extension + M4 constants

**Files:**
- Create: `helios/config/__init__.py`
- Create: `helios/config/m4_ablation.py`
- Modify: `helios/vcl/variants.py`
- Modify: `helios/vcl/__init__.py`
- Test: `tests/test_m4_ablation_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_m4_ablation_config.py`:

```python
from helios.vcl import get_all_variants


def test_get_all_variants_returns_eight_entries() -> None:
    variants = get_all_variants()
    assert len(variants) == 8


def test_get_all_variants_keys_match_confirmatory() -> None:
    from helios.vcl.variants import CONFIRMATORY_VARIANTS
    assert set(get_all_variants().keys()) == set(CONFIRMATORY_VARIANTS.keys())


def test_get_all_variants_returns_copy() -> None:
    v1 = get_all_variants()
    v2 = get_all_variants()
    assert v1 is not v2


def test_m4_expected_pipeline_row_count() -> None:
    from helios.config.m4_ablation import (
        EXPECTED_PIPELINE_ROW_COUNT,
        NUM_INCIDENTS,
        NUM_PIPELINES,
        NUM_VARIANTS,
    )
    assert NUM_INCIDENTS == 20
    assert NUM_PIPELINES == 3
    assert NUM_VARIANTS == 8
    assert EXPECTED_PIPELINE_ROW_COUNT == NUM_INCIDENTS * NUM_VARIANTS * NUM_PIPELINES


def test_hr_at_3_floor_is_positive_fraction() -> None:
    from helios.config.m4_ablation import HR_AT_3_FLOOR
    assert HR_AT_3_FLOOR > 0
    assert HR_AT_3_FLOOR < 1


def test_min_wilcoxon_pairs_is_positive_int() -> None:
    from helios.config.m4_ablation import MIN_WILCOXON_PAIRS
    assert isinstance(MIN_WILCOXON_PAIRS, int)
    assert MIN_WILCOXON_PAIRS > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_m4_ablation_config.py -v
```

Expected: `ImportError` — `helios.vcl` has no `get_all_variants` and `helios.config` does not exist.

- [ ] **Step 3: Add `get_all_variants()` to `helios/vcl/variants.py`**

After the `CONFIRMATORY_VARIANTS` dict definition, add:

```python
def get_all_variants() -> dict[str, VCLManifest]:
    """Return all confirmatory variants as a fresh dict (8 entries)."""
    return dict(CONFIRMATORY_VARIANTS)
```

- [ ] **Step 4: Export `get_all_variants` from `helios/vcl/__init__.py`**

In `helios/vcl/__init__.py`, add `get_all_variants` to the import line that brings in `CONFIRMATORY_VARIANTS`, then add it to `__all__` (maintain ASCII sort order in `__all__`).

- [ ] **Step 5: Create `helios/config/__init__.py`**

```python
"""M4 configuration constants package."""
```

- [ ] **Step 6: Create `helios/config/m4_ablation.py`**

```python
"""Frozen M4 ablation constants — single source of truth.

Any change to NUM_INCIDENTS, NUM_PIPELINES, or HR_AT_3_FLOOR requires
a deviation log entry (analytic consequence).
"""
from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl import get_all_variants

HELIOS_ENABLE_M4_ABLATION: bool = True

NUM_INCIDENTS: int = 20
NUM_PIPELINES: int = 3
NUM_VARIANTS: int = len(get_all_variants())
EXPECTED_PIPELINE_ROW_COUNT: int = NUM_INCIDENTS * NUM_VARIANTS * NUM_PIPELINES
HR_AT_3_FLOOR: float = 0.05
# Minimum paired-incident count for exact Wilcoxon; pairs below this floor are
# skipped and reported as insufficient_sample rather than zero_variance.
MIN_WILCOXON_PAIRS: int = 10
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
poetry run pytest tests/test_m4_ablation_config.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 8: Run full suite + type check**

```bash
poetry run mypy
poetry run pytest --tb=short
```

Expected: no mypy errors; all tests pass.

- [ ] **Step 9: Commit**

```bash
git add helios/config/ helios/vcl/variants.py helios/vcl/__init__.py tests/test_m4_ablation_config.py
git commit -m "feat(vcl): add get_all_variants(); add helios/config/m4_ablation constants"
```

---

### Task 3: Evaluation metrics + ground truth compiler

**Files:**
- Create: `helios/evaluation/__init__.py`
- Create: `helios/evaluation/metrics.py`
- Create: `scripts/compile_ground_truth.py`
- Test: `tests/test_metrics.py`
- Test: `tests/test_compile_ground_truth.py`

- [ ] **Step 1: Write the failing tests for hr_at_k**

Create `tests/test_metrics.py`:

```python
import pytest
from helios.evaluation.metrics import hr_at_k


def test_hr_at_k_hit_at_first_position() -> None:
    assert hr_at_k(["svc-a", "svc-b", "svc-c"], "svc-a", k=3) == 1


def test_hr_at_k_hit_at_boundary() -> None:
    assert hr_at_k(["svc-b", "svc-c", "svc-a"], "svc-a", k=3) == 1


def test_hr_at_k_miss() -> None:
    assert hr_at_k(["svc-b", "svc-c", "svc-d"], "svc-a", k=3) == 0


def test_hr_at_k_empty_verdicts() -> None:
    assert hr_at_k([], "svc-a", k=3) == 0


def test_hr_at_k_truncates_to_k() -> None:
    # svc-a is at position 3 (0-indexed 2), outside k=2 window
    assert hr_at_k(["svc-b", "svc-c", "svc-a"], "svc-a", k=2) == 0


def test_hr_at_k_returns_int() -> None:
    result = hr_at_k(["svc-a"], "svc-a", k=3)
    assert isinstance(result, int)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_metrics.py -v
```

Expected: `ModuleNotFoundError: No module named 'helios.evaluation'`

- [ ] **Step 3: Create `helios/evaluation/__init__.py`**

```python
"""Evaluation metrics for HELIOS ablation runs."""

from helios.evaluation.metrics import hr_at_k

__all__ = ["hr_at_k"]
```

- [ ] **Step 4: Create `helios/evaluation/metrics.py`**

```python
"""Hit-rate-at-k metric for RCA evaluation."""
from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_EVALUATION_METRICS: bool = True


def hr_at_k(verdicts: list[str], ground_truth: str, *, k: int) -> int:
    """Return 1 if ground_truth appears in verdicts[:k], else 0."""
    return int(ground_truth in verdicts[:k])
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_metrics.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 6: Write the failing tests for compile_ground_truth**

Create `tests/test_compile_ground_truth.py`:

```python
import json
import subprocess
import sys
import textwrap
from pathlib import Path


def test_compile_ground_truth_produces_valid_json(tmp_path: Path) -> None:
    md = textwrap.dedent("""
        | incident_id | environment | fault_injected_service | root_cause_service | fault_type | label_source | labelled_at | evaluation_phase |
        |---|---|---|---|---|---|---|---|
        | otel-001 | otel-demo | cartservice | cartservice | latency | manual | 2026-05-15 | exploratory |
        | otel-002 | otel-demo | paymentservice | paymentservice | crash | manual | 2026-05-15 | exploratory |
    """).strip()
    md_file = tmp_path / "ground_truth_labelling.md"
    md_file.write_text(md)
    out_file = tmp_path / "ground_truth.json"

    result = subprocess.run(
        [sys.executable, "scripts/compile_ground_truth.py",
         "--input", str(md_file), "--output", str(out_file)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(out_file.read_text())
    assert len(data) == 2
    assert data["otel-001"]["root_cause_service"] == "cartservice"
    assert data["otel-002"]["root_cause_service"] == "paymentservice"


def test_compile_ground_truth_no_rows_exits_nonzero(tmp_path: Path) -> None:
    md_file = tmp_path / "empty.md"
    md_file.write_text("# No table here\n")
    out_file = tmp_path / "out.json"
    result = subprocess.run(
        [sys.executable, "scripts/compile_ground_truth.py",
         "--input", str(md_file), "--output", str(out_file)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
```

- [ ] **Step 7: Run tests to verify they fail**

```bash
poetry run pytest tests/test_compile_ground_truth.py -v
```

Expected: both tests fail because `scripts/compile_ground_truth.py` does not exist.

- [ ] **Step 8: Create `scripts/compile_ground_truth.py`**

```python
#!/usr/bin/env python3
"""Parse ground_truth_labelling.md and emit data/ground_truth.json.

Usage:
    python scripts/compile_ground_truth.py [--input PATH] [--output PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_DEFAULT_INPUT = Path("docs/tracking/ground_truth_labelling.md")
_DEFAULT_OUTPUT = Path("data/ground_truth.json")


def _parse_md_table(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            if "incident_id" in cells:
                header = cells
            continue
        if re.fullmatch(r"[-| :]+", line):
            continue
        if header and len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile ground truth labels to JSON.")
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    text = args.input.read_text(encoding="utf-8")
    rows = _parse_md_table(text)
    if not rows:
        print(f"ERROR: no rows parsed from {args.input}", file=sys.stderr)
        return 1

    result = {r["incident_id"]: r for r in rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Compiled {len(result)} entries → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9: Run tests to verify they pass**

```bash
poetry run pytest tests/test_compile_ground_truth.py -v
```

Expected: both tests pass.

- [ ] **Step 10: Compile the actual ground truth file**

```bash
poetry run python scripts/compile_ground_truth.py
```

Expected: `Compiled 20 entries → data/ground_truth.json`

- [ ] **Step 11: Run full suite**

```bash
poetry run pytest --tb=short
```

- [ ] **Step 12: Commit**

```bash
git add helios/evaluation/ scripts/compile_ground_truth.py data/ground_truth.json \
    tests/test_metrics.py tests/test_compile_ground_truth.py
git commit -m "feat(eval): hr_at_k metric; compile_ground_truth.py; data/ground_truth.json"
```

---

### Task 4: ConsensusVerdict schema + integrity gate

**Files:**
- Create: `helios/consensus/__init__.py`
- Create: `helios/consensus/verdict.py`
- Test: `tests/consensus/__init__.py`
- Test: `tests/consensus/test_consensus_verdict.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/consensus/__init__.py` (empty).

Create `tests/consensus/test_consensus_verdict.py`:

```python
import pytest
from pydantic import ValidationError


def test_consensus_verdict_valid_construction() -> None:
    from helios.consensus.verdict import ConsensusVerdict
    cv = ConsensusVerdict(
        incident_id="otel-001",
        variant="HELIOS-Full",
        top_candidates=["svc-a", "svc-b", "svc-c"],
        borda_scores={"svc-a": 2, "svc-b": 1, "svc-c": 0},
        candidate_universe_size=3,
        consensus_rank=3,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha="abc123",
        pipeline_row_count=3,
        run_id="run-001",
        timestamp_utc="2026-05-20T10:00:00Z",
    )
    assert cv.incident_id == "otel-001"
    assert cv.pipeline_row_count == 3
    assert cv.candidate_universe_size == 3


def test_consensus_verdict_cpr_defaults_to_zero() -> None:
    from helios.consensus.verdict import CPR_PENDING, ConsensusVerdict
    cv = ConsensusVerdict(
        incident_id="otel-001",
        variant="HELIOS-Full",
        top_candidates=["svc-a"],
        borda_scores={"svc-a": 2},
        candidate_universe_size=1,
        consensus_rank=1,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha="abc123",
        pipeline_row_count=3,
        run_id="run-001",
        timestamp_utc="2026-05-20T10:00:00Z",
    )
    assert cv.cpr == CPR_PENDING


def test_consensus_verdict_empty_candidates_rejected() -> None:
    from helios.consensus.verdict import ConsensusVerdict
    with pytest.raises(ValidationError):
        ConsensusVerdict(
            incident_id="otel-001",
            variant="HELIOS-Full",
            top_candidates=[],
            borda_scores={},
            candidate_universe_size=1,
            consensus_rank=0,
            fusion_algorithm="borda-v1",
            fusion_algorithm_sha="abc123",
            pipeline_row_count=3,
            run_id="run-001",
            timestamp_utc="2026-05-20T10:00:00Z",
        )


def test_consensus_integrity_gate_passes_matching_sha() -> None:
    from helios.consensus.verdict import ConsensusIntegrityGate, ConsensusVerdict
    sha = "deadbeef"
    cv = ConsensusVerdict(
        incident_id="otel-001",
        variant="HELIOS-Full",
        top_candidates=["svc-a"],
        borda_scores={"svc-a": 2},
        candidate_universe_size=1,
        consensus_rank=1,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha=sha,
        pipeline_row_count=3,
        run_id="run-001",
        timestamp_utc="2026-05-20T10:00:00Z",
    )
    gate = ConsensusIntegrityGate(expected_sha=sha)
    gate.check(cv)  # must not raise


def test_consensus_integrity_gate_raises_on_sha_mismatch() -> None:
    from helios.consensus.verdict import ConsensusIntegrityGate, ConsensusVerdict
    cv = ConsensusVerdict(
        incident_id="otel-001",
        variant="HELIOS-Full",
        top_candidates=["svc-a"],
        borda_scores={"svc-a": 2},
        candidate_universe_size=1,
        consensus_rank=1,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha="sha-stored",
        pipeline_row_count=3,
        run_id="run-001",
        timestamp_utc="2026-05-20T10:00:00Z",
    )
    gate = ConsensusIntegrityGate(expected_sha="sha-different")
    with pytest.raises(ValueError, match="fusion_algorithm_sha mismatch"):
        gate.check(cv)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/consensus/test_consensus_verdict.py -v
```

Expected: `ModuleNotFoundError: No module named 'helios.consensus'`

- [ ] **Step 3: Create `helios/consensus/verdict.py`**

```python
"""ConsensusVerdict schema and integrity gate.

schema-draft-v0.3 — not to be confused with PipelineVerdict schema-draft-v0.2.
CPR is a Stage 5 field; it is set to CPR_PENDING until cost data is available.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_CONSENSUS_VERDICT: bool = True

CPR_PENDING: float = float("0")

SCHEMA_VERSION: str = "schema-draft-v0.3"


class ConsensusVerdict(BaseModel, frozen=True):
    incident_id: str
    variant: str
    top_candidates: list[str] = Field(min_length=1)
    borda_scores: dict[str, float]
    # borda_scores are per-incident relative values (scored against the local
    # candidate union of size candidate_universe_size). They must not be compared
    # across incidents; downstream statistical analysis uses hr_at_3 (binary).
    # Store candidate_universe_size so future post-hoc normalization is possible
    # without reprocessing: normalised_score = borda_scores[c] / candidate_universe_size.
    candidate_universe_size: int = Field(ge=1)
    consensus_rank: int = Field(ge=1)
    fusion_algorithm: str
    fusion_algorithm_sha: str
    cpr: float = Field(default=CPR_PENDING)
    pipeline_row_count: int = Field(ge=1)
    run_id: str
    timestamp_utc: str

    @model_validator(mode="after")
    def _top_candidates_in_scores(self) -> "ConsensusVerdict":
        missing = [c for c in self.top_candidates if c not in self.borda_scores]
        if missing:
            raise ValueError(f"top_candidates not in borda_scores: {missing}")
        return self


class ConsensusIntegrityGate:
    """Verifies that a ConsensusVerdict's fusion_algorithm_sha matches the expected value."""

    def __init__(self, *, expected_sha: str) -> None:
        self._expected_sha = expected_sha

    def check(self, cv: ConsensusVerdict) -> None:
        if cv.fusion_algorithm_sha != self._expected_sha:
            raise ValueError(
                f"fusion_algorithm_sha mismatch: stored={cv.fusion_algorithm_sha!r}, "
                f"expected={self._expected_sha!r}"
            )
```

- [ ] **Step 4: Create `helios/consensus/__init__.py`**

```python
"""Consensus layer: UniformBorda fusion and ConsensusVerdict schema."""

from helios.consensus.verdict import (
    CPR_PENDING,
    SCHEMA_VERSION,
    ConsensusIntegrityGate,
    ConsensusVerdict,
)

__all__ = [
    "CPR_PENDING",
    "ConsensusIntegrityGate",
    "ConsensusVerdict",
    "SCHEMA_VERSION",
]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/consensus/test_consensus_verdict.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 6: Run full suite + mypy**

```bash
poetry run mypy
poetry run pytest --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add helios/consensus/ tests/consensus/__init__.py tests/consensus/test_consensus_verdict.py
git commit -m "feat(consensus): ConsensusVerdict schema-draft-v0.3 + ConsensusIntegrityGate"
```

---

### Task 5: Store schema extension + result_store methods

**Files:**
- Modify: `helios/store/schema.sql`
- Modify: `helios/store/result_store.py`
- Test: extend `tests/test_result_store.py`

- [ ] **Step 1: Read the current schema.sql and result_store.py**

```bash
cat helios/store/schema.sql
grep -n "def " helios/store/result_store.py
```

Confirm: `result_row` table exists (schema-draft-v0.2); `insert`, `fetch_all`, `fetch_all_for_incident`, `inclusion_rate`, `close` methods exist.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_result_store.py` (or create it if absent):

```python
import json
from pathlib import Path

import pytest

from helios.consensus.verdict import ConsensusVerdict, CPR_PENDING


def _make_cv(incident_id: str = "otel-001", variant: str = "HELIOS-Full") -> ConsensusVerdict:
    return ConsensusVerdict(
        incident_id=incident_id,
        variant=variant,
        top_candidates=["svc-a", "svc-b"],
        borda_scores={"svc-a": 2, "svc-b": 1},
        candidate_universe_size=2,
        consensus_rank=2,
        fusion_algorithm="borda-v1",
        fusion_algorithm_sha="abc123",
        pipeline_row_count=3,
        run_id="run-test",
        timestamp_utc="2026-05-20T10:00:00Z",
    )


def test_insert_and_fetch_consensus(tmp_path: Path) -> None:
    from helios.store.result_store import ResultStore
    store = ResultStore(tmp_path / "test.duckdb")
    cv = _make_cv()
    store.insert_consensus(cv)
    rows = store.fetch_all_consensus_rows()
    assert len(rows) == 1
    assert rows[0]["incident_id"] == "otel-001"
    assert rows[0]["variant"] == "HELIOS-Full"
    store.close()


def test_fetch_all_pipeline_rows_returns_list(tmp_path: Path) -> None:
    from helios.store.result_store import ResultStore
    store = ResultStore(tmp_path / "test.duckdb")
    rows = store.fetch_all_pipeline_rows()
    assert isinstance(rows, list)
    store.close()


def test_insert_consensus_idempotent_guard(tmp_path: Path) -> None:
    from helios.store.result_store import ResultStore
    store = ResultStore(tmp_path / "test.duckdb")
    cv = _make_cv()
    store.insert_consensus(cv)
    # Second insert of same (incident_id, variant) must not raise — INSERT OR IGNORE
    store.insert_consensus(cv)
    rows = store.fetch_all_consensus_rows()
    assert len(rows) == 1
    store.close()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
poetry run pytest tests/test_result_store.py -v -k "consensus"
```

Expected: `AttributeError` — `ResultStore` has no `insert_consensus` or `fetch_all_consensus_rows`.

- [ ] **Step 4: Add `consensus_verdict` table to `helios/store/schema.sql`**

Append to `helios/store/schema.sql`:

```sql
-- schema-draft-v0.3: consensus verdict table
CREATE TABLE IF NOT EXISTS consensus_verdict (
    incident_id              VARCHAR NOT NULL,
    variant                  VARCHAR NOT NULL,
    top_candidates           VARCHAR NOT NULL,  -- JSON array string
    borda_scores             VARCHAR NOT NULL,  -- JSON object string (per-incident relative; see candidate_universe_size)
    candidate_universe_size  INTEGER NOT NULL,  -- |all_candidates| for this incident; enables post-hoc normalisation
    consensus_rank           INTEGER NOT NULL,
    fusion_algorithm         VARCHAR NOT NULL,
    fusion_algorithm_sha     VARCHAR NOT NULL,
    cpr                      DOUBLE  NOT NULL DEFAULT 0,
    pipeline_row_count       INTEGER NOT NULL,
    run_id                   VARCHAR NOT NULL,
    timestamp_utc            VARCHAR NOT NULL,
    PRIMARY KEY (incident_id, variant)
);
```

Also update the `schema_tag` insertion in the SQL file from `schema-draft-v0.2` to `schema-draft-v0.3`:

```sql
INSERT OR IGNORE INTO schema_tag(tag) VALUES ('schema-draft-v0.3');
```

- [ ] **Step 5: Add methods to `helios/store/result_store.py`**

Inside the `ResultStore` class, add after the existing `inclusion_rate` method:

```python
def insert_consensus(self, cv: "ConsensusVerdict") -> None:
    import json as _json
    self._conn.execute(
        """
        INSERT OR IGNORE INTO consensus_verdict
        (incident_id, variant, top_candidates, borda_scores, candidate_universe_size,
         consensus_rank, fusion_algorithm, fusion_algorithm_sha, cpr,
         pipeline_row_count, run_id, timestamp_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            cv.incident_id,
            cv.variant,
            _json.dumps(cv.top_candidates),
            _json.dumps(cv.borda_scores),
            cv.candidate_universe_size,
            cv.consensus_rank,
            cv.fusion_algorithm,
            cv.fusion_algorithm_sha,
            cv.cpr,
            cv.pipeline_row_count,
            cv.run_id,
            cv.timestamp_utc,
        ],
    )

def fetch_all_pipeline_rows(self) -> list[dict]:
    rows = self._conn.execute("SELECT * FROM result_row").fetchall()
    cols = [d[0] for d in self._conn.description]
    return [dict(zip(cols, row)) for row in rows]

def fetch_all_consensus_rows(self) -> list[dict]:
    rows = self._conn.execute("SELECT * FROM consensus_verdict").fetchall()
    cols = [d[0] for d in self._conn.description]
    return [dict(zip(cols, row)) for row in rows]
```

You will need to add `TYPE_CHECKING` guard for `ConsensusVerdict` import:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from helios.consensus.verdict import ConsensusVerdict
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
poetry run pytest tests/test_result_store.py -v
```

Expected: all result_store tests pass including the new consensus tests.

- [ ] **Step 7: Run full suite**

```bash
poetry run mypy
poetry run pytest --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add helios/store/schema.sql helios/store/result_store.py tests/test_result_store.py
git commit -m "feat(store): schema-draft-v0.3 consensus_verdict table; insert/fetch_consensus methods"
```

---

### Task 6: UniformBorda + PassthroughConsensus

**Files:**
- Create: `helios/consensus/uniform_borda.py`
- Test: `tests/consensus/test_uniform_borda.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/consensus/test_uniform_borda.py`:

```python
import pytest

from helios.consensus.verdict import ConsensusVerdict


def _make_pipeline_rows(candidates_per_pipe: list[list[str]]) -> list[dict]:
    """Build mock pipeline rows from ranked candidate lists."""
    pipes = ["d_pipe", "g_pipe", "l_pipe"]
    rows = []
    for pipe, candidates in zip(pipes, candidates_per_pipe):
        rows.append({
            "pipeline": pipe,
            "ranked_candidates": candidates,
            "narrative": "normal",
        })
    return rows


def test_uniform_borda_fuse_clear_winner() -> None:
    from helios.consensus.uniform_borda import UniformBordaConsensus
    borda = UniformBordaConsensus()
    rows = _make_pipeline_rows([
        ["svc-a", "svc-b", "svc-c"],
        ["svc-a", "svc-c", "svc-b"],
        ["svc-a", "svc-b", "svc-c"],
    ])
    result = borda.fuse(incident_id="otel-001", variant="HELIOS-Full",
                        pipeline_rows=rows, run_id="r1")
    assert isinstance(result, ConsensusVerdict)
    assert result.top_candidates[0] == "svc-a"
    assert result.pipeline_row_count == 3


def test_uniform_borda_tie_broken_alphabetically() -> None:
    from helios.consensus.uniform_borda import UniformBordaConsensus
    borda = UniformBordaConsensus()
    rows = _make_pipeline_rows([
        ["svc-a", "svc-b"],
        ["svc-b", "svc-a"],
        ["svc-a", "svc-b"],
    ])
    result = borda.fuse(incident_id="otel-001", variant="HELIOS-Full",
                        pipeline_rows=rows, run_id="r1")
    # svc-a and svc-b have equal Borda scores after one round; alphabetical tiebreak
    assert result.top_candidates[0] in ("svc-a", "svc-b")
    # Deterministic: run twice, same order
    result2 = borda.fuse(incident_id="otel-001", variant="HELIOS-Full",
                         pipeline_rows=rows, run_id="r1")
    assert result.top_candidates == result2.top_candidates


def test_uniform_borda_fusion_algorithm_frozen() -> None:
    from helios.consensus.uniform_borda import FUSION_CORE_VERSION, UniformBordaConsensus
    borda = UniformBordaConsensus()
    rows = _make_pipeline_rows([["svc-a"], ["svc-a"], ["svc-a"]])
    result = borda.fuse(incident_id="otel-001", variant="HELIOS-Full",
                        pipeline_rows=rows, run_id="r1")
    assert result.fusion_algorithm == FUSION_CORE_VERSION


def test_fusion_algorithm_sha_is_stable() -> None:
    from helios.consensus.uniform_borda import FUSION_ALGORITHM_SHA
    assert len(FUSION_ALGORITHM_SHA) == 64  # sha256 hex digest
    # Importing again must return the same SHA
    import importlib
    import helios.consensus.uniform_borda as mod
    assert mod.FUSION_ALGORITHM_SHA == FUSION_ALGORITHM_SHA


def test_passthrough_consensus_propagates_top_verdict() -> None:
    from helios.consensus.uniform_borda import PassthroughConsensus
    pt = PassthroughConsensus()
    rows = _make_pipeline_rows([
        ["svc-x", "svc-y"],
        ["svc-x", "svc-z"],
        ["svc-y", "svc-x"],
    ])
    result = pt.fuse(incident_id="otel-001", variant="HELIOS-noConsensus",
                     pipeline_rows=rows, run_id="r1")
    assert isinstance(result, ConsensusVerdict)
    assert result.fusion_algorithm == "passthrough"
    assert len(result.top_candidates) >= 1


def test_uniform_borda_empty_pipeline_rows_raises() -> None:
    from helios.consensus.uniform_borda import UniformBordaConsensus
    borda = UniformBordaConsensus()
    with pytest.raises(ValueError, match="pipeline_rows"):
        borda.fuse(incident_id="otel-001", variant="HELIOS-Full",
                   pipeline_rows=[], run_id="r1")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/consensus/test_uniform_borda.py -v
```

Expected: `ImportError` — `helios.consensus.uniform_borda` does not exist.

- [ ] **Step 3: Create `helios/consensus/uniform_borda.py`**

```python
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
from helios.vcl import GatedComponentInactiveError, VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.decorators import gated_by

HELIOS_ENABLE_UNIFORM_BORDA: bool = True

FUSION_CORE_VERSION: str = "borda-v1"


class _StripDocstrings(ast.NodeTransformer):
    """Remove string-literal docstrings from function/class/module bodies.

    Safety invariants:
    - Only strips when len(body) > 1 to prevent leaving an empty body.
    - Only strips str constants, so `...` stubs are preserved.
    - Uses NodeTransformer (not ast.walk + mutation) to avoid iterator
      invalidation during tree traversal.
    """

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

    visit_FunctionDef = _strip
    visit_AsyncFunctionDef = _strip
    visit_ClassDef = _strip
    visit_Module = _strip


_REQUIRED_PYTHON_MINOR: tuple[int, int] = (3, 11)


def _compute_ast_hash() -> str:
    """Compute a stable SHA-256 of this module's AST with docstrings stripped.

    Uses ``Path(__file__).read_text()`` rather than ``inspect.getmodule`` to
    avoid two failure modes:
    - ``inspect.getmodule`` returns ``None`` when the module is imported under
      a dynamic alias or loaded via importlib without a proper module entry.
    - ``inspect.getmodule`` returns the ``__main__`` module when this file is
      executed directly, returning source that may differ from the installed
      package source.

    ``ast.dump()`` output is stable only within a Python minor version — node
    attributes added in 3.12 produce a different digest than 3.11. A runtime
    guard enforces the version at import time so mismatches surface immediately
    rather than silently producing an unverifiable SHA.
    """
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
    """Uniform Borda count fusion over 3 peer-pipeline ranked lists."""

    @gated_by(VCLFlag.CONSENSUS)
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

        # Collect all unique candidates across all pipelines
        all_candidates: set[str] = set()
        for row in pipeline_rows:
            all_candidates.update(row.get("ranked_candidates", []))

        # Uniform Borda: score on global universe size N so all pipelines are
        # weighted equally regardless of their output cardinality.
        # Position i in any pipeline's ranked list → N - i - 1 points.
        # Candidates absent from a pipeline's list implicitly receive 0.
        #
        # N is the candidate union for *this incident only* — borda_scores are
        # therefore per-incident relative values and must not be compared across
        # incidents. Downstream statistics (Wilcoxon) operate on hr_at_3 (binary
        # hit-rate), which is derived from the ranking order, not from raw scores.
        N = len(all_candidates)
        scores: dict[str, float] = {c: float(0) for c in all_candidates}
        for row in pipeline_rows:
            ranked = row.get("ranked_candidates", [])
            for i, candidate in enumerate(ranked):
                if candidate in scores:
                    scores[candidate] += N - i - 1

        # Deterministic tiebreak: sort by (-score, name)
        ordered = sorted(all_candidates, key=lambda c: (-scores[c], c))

        return ConsensusVerdict(
            incident_id=incident_id,
            variant=variant,
            top_candidates=ordered,
            borda_scores=scores,
            candidate_universe_size=N,
            consensus_rank=len(ordered),
            fusion_algorithm=FUSION_CORE_VERSION,
            fusion_algorithm_sha=FUSION_ALGORITHM_SHA,
            cpr=CPR_PENDING,
            pipeline_row_count=len(pipeline_rows),
            run_id=run_id,
            timestamp_utc=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )


_PASSTHROUGH_PIPELINE_PRIORITY: tuple[str, ...] = ("d_pipe", "g_pipe", "l_pipe")
"""Pipeline priority for PassthroughConsensus fallback.

When the CONSENSUS flag is disabled, top candidates are taken from the
highest-priority pipeline that returned results for that incident. D-pipe
is first because it is the statistical baseline and always runs. This is
an explicit design choice — not alphabetical ordering — so downstream
ablation results for HELIOS-noConsensus reflect D-pipe accuracy as the
"no fusion" reference point.
"""


class PassthroughConsensus:
    """Passthrough for variants with consensus disabled.

    Propagates the top candidates list from the highest-priority available
    pipeline (see _PASSTHROUGH_PIPELINE_PRIORITY). Used when
    GatedComponentInactiveError would be raised by UniformBordaConsensus.
    """

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

        # Order rows by explicit priority (not alphabetical) so top candidates
        # come from the designated baseline pipeline (_PASSTHROUGH_PIPELINE_PRIORITY).
        priority_index = {p: i for i, p in enumerate(_PASSTHROUGH_PIPELINE_PRIORITY)}
        sorted_rows = sorted(
            pipeline_rows,
            key=lambda r: priority_index.get(r.get("pipeline", ""), len(_PASSTHROUGH_PIPELINE_PRIORITY)),
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
            raise ValueError(f"No ranked candidates found in pipeline_rows for {incident_id}")

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
            timestamp_utc=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
```

- [ ] **Step 4: Export from `helios/consensus/__init__.py`**

Update `helios/consensus/__init__.py` to also export `UniformBordaConsensus`, `PassthroughConsensus`, and `FUSION_ALGORITHM_SHA`:

```python
"""Consensus layer: UniformBorda fusion and ConsensusVerdict schema."""

from helios.consensus.uniform_borda import (
    FUSION_ALGORITHM_SHA,
    FUSION_CORE_VERSION,
    PassthroughConsensus,
    UniformBordaConsensus,
)
from helios.consensus.verdict import (
    CPR_PENDING,
    SCHEMA_VERSION,
    ConsensusIntegrityGate,
    ConsensusVerdict,
)

__all__ = [
    "CPR_PENDING",
    "ConsensusIntegrityGate",
    "ConsensusVerdict",
    "FUSION_ALGORITHM_SHA",
    "FUSION_CORE_VERSION",
    "PassthroughConsensus",
    "SCHEMA_VERSION",
    "UniformBordaConsensus",
]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/consensus/test_uniform_borda.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 6: Run full suite + lint**

```bash
poetry run ruff check helios/ tests/ && poetry run mypy && poetry run pytest --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add helios/consensus/ tests/consensus/test_uniform_borda.py
git commit -m "feat(consensus): UniformBordaConsensus, PassthroughConsensus, AST SHA anchor"
```

---

### Task 7: Property-based tests for Borda

**Files:**
- Test: `tests/consensus/test_uniform_borda_property.py`

- [ ] **Step 1: Write the property tests**

Create `tests/consensus/test_uniform_borda_property.py`:

```python
"""Hypothesis property tests for UniformBordaConsensus."""
from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from helios.consensus.uniform_borda import UniformBordaConsensus
from helios.consensus.verdict import ConsensusVerdict


_NAMES = st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=2, max_size=8)
_CANDIDATE_LIST = st.lists(_NAMES, min_size=1, max_size=5, unique=True)


def _build_rows(ranked_lists: list[list[str]]) -> list[dict]:
    pipes = ["d_pipe", "g_pipe", "l_pipe"]
    return [
        {"pipeline": p, "ranked_candidates": r, "narrative": "normal"}
        for p, r in zip(pipes, ranked_lists)
    ]


@given(
    ranked_lists=st.lists(_CANDIDATE_LIST, min_size=1, max_size=3),
)
@settings(max_examples=50)
def test_fuse_result_is_consensus_verdict(ranked_lists: list[list[str]]) -> None:
    borda = UniformBordaConsensus()
    rows = _build_rows(ranked_lists)
    result = borda.fuse(
        incident_id="otel-prop", variant="HELIOS-Full",
        pipeline_rows=rows, run_id="prop-run",
    )
    assert isinstance(result, ConsensusVerdict)


@given(
    ranked_lists=st.lists(_CANDIDATE_LIST, min_size=1, max_size=3),
)
@settings(max_examples=50)
def test_fuse_top_candidate_is_in_some_pipeline(ranked_lists: list[list[str]]) -> None:
    all_candidates = {c for lst in ranked_lists for c in lst}
    borda = UniformBordaConsensus()
    rows = _build_rows(ranked_lists)
    result = borda.fuse(
        incident_id="otel-prop", variant="HELIOS-Full",
        pipeline_rows=rows, run_id="prop-run",
    )
    assert result.top_candidates[0] in all_candidates


@given(
    candidates=st.lists(_NAMES, min_size=2, max_size=4, unique=True),
)
@settings(max_examples=30)
def test_fuse_is_deterministic_across_calls(candidates: list[str]) -> None:
    borda = UniformBordaConsensus()
    rows = _build_rows([candidates, list(reversed(candidates)), candidates])
    r1 = borda.fuse(incident_id="otel-det", variant="HELIOS-Full",
                    pipeline_rows=rows, run_id="run-1")
    r2 = borda.fuse(incident_id="otel-det", variant="HELIOS-Full",
                    pipeline_rows=rows, run_id="run-1")
    assert r1.top_candidates == r2.top_candidates


@given(
    ranked_lists=st.lists(_CANDIDATE_LIST, min_size=1, max_size=3),
)
@settings(max_examples=30)
def test_fuse_pipeline_row_count_matches_input(ranked_lists: list[list[str]]) -> None:
    borda = UniformBordaConsensus()
    rows = _build_rows(ranked_lists)
    result = borda.fuse(
        incident_id="otel-prop", variant="HELIOS-Full",
        pipeline_rows=rows, run_id="prop-run",
    )
    assert result.pipeline_row_count == len(rows)
```

- [ ] **Step 2: Run property tests to verify they pass**

```bash
poetry run pytest tests/consensus/test_uniform_borda_property.py -v
```

Expected: all 4 property tests pass with hypothesis-generated examples.

- [ ] **Step 3: Run full suite**

```bash
poetry run pytest --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add tests/consensus/test_uniform_borda_property.py
git commit -m "test(consensus): hypothesis property tests for UniformBordaConsensus"
```

---

### Task 8: Ledger OUTCOMES extension

**Files:**
- Modify: `helios/orchestrator/ledger.py`
- Test: extend `tests/test_ledger.py` (or create if absent)

- [ ] **Step 1: Read the current OUTCOMES frozenset**

```bash
grep -n "OUTCOMES" helios/orchestrator/ledger.py
```

Confirm the current value: `frozenset({"attempted", "passed", "excluded", "skipped"})`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_ledger.py`:

```python
def test_outcomes_includes_consensus_computed() -> None:
    from helios.orchestrator.ledger import OUTCOMES
    assert "consensus_computed" in OUTCOMES


def test_outcomes_includes_consensus_skipped() -> None:
    from helios.orchestrator.ledger import OUTCOMES
    assert "consensus_skipped" in OUTCOMES


def test_outcomes_includes_consensus_excluded() -> None:
    from helios.orchestrator.ledger import OUTCOMES
    assert "consensus_excluded" in OUTCOMES
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
poetry run pytest tests/test_ledger.py -v -k "consensus"
```

Expected: `AssertionError` — the new outcomes are not in OUTCOMES yet.

- [ ] **Step 4: Update OUTCOMES in `helios/orchestrator/ledger.py`**

Find the line defining `OUTCOMES` and update it to include the three new values:

```python
OUTCOMES: frozenset[str] = frozenset({
    "attempted",
    "consensus_computed",
    "consensus_excluded",
    "consensus_skipped",
    "excluded",
    "passed",
    "skipped",
})
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_ledger.py -v
```

Expected: all ledger tests pass including the 3 new ones.

- [ ] **Step 6: Run full suite**

```bash
poetry run pytest --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add helios/orchestrator/ledger.py tests/test_ledger.py
git commit -m "feat(ledger): add consensus_computed, consensus_skipped, consensus_excluded OUTCOMES"
```

---

### Task 9: run_one_variant.py + run_ablation.py (with integration test)

**Files:**
- Create: `scripts/run_one_variant.py`
- Create: `scripts/run_ablation.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_run_ablation_dry_run.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/__init__.py` (empty).

Create `tests/integration/test_run_ablation_dry_run.py`:

```python
"""Integration tests for run_ablation.py --dry-run mode."""
import subprocess
import sys
from pathlib import Path


def test_dry_run_exits_zero(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_ablation.py",
         "--dry-run", "--output-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_dry_run_prints_variant_list(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_ablation.py",
         "--dry-run", "--output-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    # Must list all 8 confirmatory variants
    for name in ["HELIOS-Full", "HELIOS-noLLM", "HELIOS-noGraph", "HELIOS-D"]:
        assert name in result.stdout, f"{name} not in output"


def test_dry_run_prints_expected_row_count(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_ablation.py",
         "--dry-run", "--output-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert "480" in result.stdout, f"Expected 480 in output, got: {result.stdout}"


def test_dry_run_does_not_create_db_files(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "scripts/run_ablation.py",
         "--dry-run", "--output-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    db_files = list(tmp_path.glob("*.duckdb"))
    assert db_files == [], f"Unexpected DB files created: {db_files}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/integration/test_run_ablation_dry_run.py -v
```

Expected: all 4 tests fail — `scripts/run_ablation.py` does not exist.

- [ ] **Step 3: Create `scripts/run_one_variant.py`**

```python
#!/usr/bin/env python3
"""Subprocess entry point: run RunOrchestrator for a single named variant.

Called by run_ablation.py via subprocess.run(). Accepts CLI args for the
variant name, DB output path, and data directory.

Usage:
    python scripts/run_one_variant.py --variant HELIOS-Full \\
        --db-path /tmp/helios/HELIOS-Full.duckdb \\
        --captures-dir data/captures \\
        --registry-path data/snapshot_registry.jsonl \\
        --reconciliation-path data/reconciliation_ledger.jsonl \\
        --exclusion-ledger exclusion_ledger.jsonl
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one HELIOS variant.")
    parser.add_argument("--variant", required=True)
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--captures-dir", type=Path, required=True)
    parser.add_argument("--registry-path", type=Path, required=True)
    parser.add_argument("--reconciliation-path", type=Path, required=True)
    parser.add_argument("--exclusion-ledger", type=Path, required=True)
    args = parser.parse_args(argv)

    hmac_key = os.environ.get("DEVIATION_HMAC_SECRET", "")

    from helios.vcl import get_variant, set_current_manifest
    from helios.orchestrator.runner import RunOrchestrator

    manifest = get_variant(args.variant)
    set_current_manifest(manifest)

    orchestrator = RunOrchestrator(
        manifest=manifest,
        captures_dir=args.captures_dir,
        db_path=args.db_path,
        registry_path=args.registry_path,
        reconciliation_path=args.reconciliation_path,
        exclusion_ledger=args.exclusion_ledger,
        hmac_key=hmac_key,
    )
    orchestrator.run(corpus=args.captures_dir)
    print(f"[run_one_variant] {args.variant} complete → {args.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Create `scripts/run_ablation.py`**

```python
#!/usr/bin/env python3
"""Run the full HELIOS ablation matrix.

Spawns one subprocess per variant (run_one_variant.py), then atomically
merges all per-variant DuckDB files into a central DB.

Usage:
    python scripts/run_ablation.py --output-dir /tmp/helios-m4
    python scripts/run_ablation.py --dry-run --output-dir /tmp/helios-m4
    python scripts/run_ablation.py --output-dir /tmp/helios-m4 --rollback-on-failure
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from helios.config.m4_ablation import EXPECTED_PIPELINE_ROW_COUNT, NUM_VARIANTS
from helios.vcl import get_all_variants


def _dry_run(output_dir: Path) -> int:
    variants = list(get_all_variants().keys())
    print("DRY RUN — no subprocesses spawned")
    print(f"Variants ({NUM_VARIANTS}):")
    for v in variants:
        print(f"  {v}")
    print(f"Expected total pipeline rows: {EXPECTED_PIPELINE_ROW_COUNT}")
    print(f"Output directory (would be created): {output_dir}")
    return 0


_DEFAULT_VARIANT_TIMEOUT_SECONDS: int = 7200  # 2 h; L-pipe × 3 samples × 20 incidents


def _run_variant_subprocess(
    variant_name: str,
    db_path: Path,
    captures_dir: Path,
    registry_path: Path,
    reconciliation_path: Path,
    exclusion_ledger: Path,
    *,
    timeout: int,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, "scripts/run_one_variant.py",
            "--variant", variant_name,
            "--db-path", str(db_path),
            "--captures-dir", str(captures_dir),
            "--registry-path", str(registry_path),
            "--reconciliation-path", str(reconciliation_path),
            "--exclusion-ledger", str(exclusion_ledger),
        ],
        capture_output=False,
        timeout=timeout,
    )


def _atomic_merge(per_variant_dbs: list[Path], central_db: Path) -> None:
    """Merge all per-variant DBs into central_db atomically.

    Uses a single DuckDB transaction wrapping all inserts:
    - All sources are ATTACHed before the transaction begins.
    - All INSERT OR IGNORE statements run inside one BEGIN/COMMIT block.
    - On any exception, DuckDB rolls back automatically; on SIGKILL, the
      uncommitted WAL is discarded on next open.  No manual backup needed.
    - DETACH runs in a finally block regardless of outcome.
    """
    import duckdb
    aliases: list[str] = []
    conn = duckdb.connect(str(central_db))
    try:
        # Attach all sources before opening the transaction (ATTACH is DDL
        # and not transactional in DuckDB).
        for idx, db_path in enumerate(per_variant_dbs):
            alias = f"src_{idx}"
            conn.execute(f"ATTACH '{db_path!s}' AS {alias} (READ_ONLY)")
            aliases.append(alias)

        # Wrap all inserts in one transaction for all-or-nothing atomicity.
        conn.begin()
        try:
            for alias in aliases:
                conn.execute(
                    f"INSERT OR IGNORE INTO result_row SELECT * FROM {alias}.result_row"
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        for alias in aliases:
            try:
                conn.execute(f"DETACH {alias}")
            except Exception:
                pass
        conn.close()


def _smoke_check(central_db: Path, expected_variants: list[str]) -> bool:
    import duckdb
    conn = duckdb.connect(str(central_db), read_only=True)
    total = conn.execute("SELECT COUNT(*) FROM result_row").fetchone()[0]
    found = {
        r[0]
        for r in conn.execute("SELECT DISTINCT variant FROM result_row").fetchall()
    }
    conn.close()
    missing = set(expected_variants) - found
    if missing:
        print(f"Smoke check FAIL: missing variants: {missing}", file=sys.stderr)
        return False
    print(
        f"Smoke check OK: {total} pipeline rows, "
        f"{len(found)}/{len(expected_variants)} variants present in {central_db}"
    )
    return total > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run HELIOS ablation matrix.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--captures-dir", type=Path, default=Path("data/captures"))
    parser.add_argument("--registry-path", type=Path, default=Path("data/snapshot_registry.jsonl"))
    parser.add_argument(
        "--reconciliation-path",
        type=Path, default=Path("data/reconciliation_ledger.jsonl"),
    )
    parser.add_argument("--exclusion-ledger", type=Path, default=Path("exclusion_ledger.jsonl"))
    parser.add_argument(
        "--variant-timeout",
        type=int,
        default=_DEFAULT_VARIANT_TIMEOUT_SECONDS,
        help=f"Per-variant subprocess timeout in seconds (default: {_DEFAULT_VARIANT_TIMEOUT_SECONDS})",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        return _dry_run(args.output_dir)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    variants = get_all_variants()
    per_variant_dbs: list[Path] = []
    failed: list[str] = []

    # Sequential execution only — DuckDB files are not concurrency-safe.
    # Do NOT parallelize this loop externally (e.g., GNU parallel, multiprocessing).
    for name in variants:
        db_path = args.output_dir / f"{name}.duckdb"
        print(f"Running variant: {name}")
        try:
            proc = _run_variant_subprocess(
                variant_name=name,
                db_path=db_path,
                captures_dir=args.captures_dir,
                registry_path=args.registry_path,
                reconciliation_path=args.reconciliation_path,
                exclusion_ledger=args.exclusion_ledger,
                timeout=args.variant_timeout,
            )
        except subprocess.TimeoutExpired:
            failed.append(name)
            print(
                f"  TIMEOUT: {name} exceeded {args.variant_timeout}s",
                file=sys.stderr,
            )
            continue
        if proc.returncode != 0:
            failed.append(name)
            print(f"  FAILED: {name} exited {proc.returncode}", file=sys.stderr)
        else:
            per_variant_dbs.append(db_path)

    if failed:
        print(f"Variants failed: {failed}", file=sys.stderr)
        return 1

    central_db = args.output_dir / "helios_m4_results.duckdb"
    # _atomic_merge wraps all inserts in a single DuckDB transaction.
    # Rollback is automatic on failure — no manual backup/restore needed.
    try:
        _atomic_merge(per_variant_dbs, central_db)
    except Exception as exc:
        print(f"Merge failed: {exc}", file=sys.stderr)
        return 1

    if not _smoke_check(central_db, list(variants.keys())):
        print("Smoke check failed: see details above", file=sys.stderr)
        return 1

    print(f"Ablation run complete. Results at {central_db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run integration tests to verify they pass**

```bash
poetry run pytest tests/integration/test_run_ablation_dry_run.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 6: Verify scripts parse cleanly (no import errors)**

```bash
poetry run python -c "import ast, pathlib; ast.parse(pathlib.Path('scripts/run_one_variant.py').read_text())"
poetry run python -c "import ast, pathlib; ast.parse(pathlib.Path('scripts/run_ablation.py').read_text())"
```

Expected: both exit 0 without output.

- [ ] **Step 7: Run full suite**

```bash
poetry run mypy
poetry run pytest --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add scripts/run_one_variant.py scripts/run_ablation.py \
    tests/integration/__init__.py tests/integration/test_run_ablation_dry_run.py
git commit -m "feat(runner): run_one_variant.py + run_ablation.py with dry-run; integration tests"
```

---

### Task 10: fuse_verdicts.py

**Files:**
- Create: `scripts/fuse_verdicts.py`
- Test: `tests/integration/test_fuse_verdicts.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_fuse_verdicts.py`:

```python
"""Integration tests for fuse_verdicts.py."""
import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest


def _create_minimal_result_db(db_path: Path, variant: str) -> None:
    """Create a minimal DuckDB result_row table with 3 pipeline rows for 1 incident."""
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE result_row (
            incident_id VARCHAR,
            variant VARCHAR,
            pipeline VARCHAR,
            ranked_candidates VARCHAR,
            narrative VARCHAR,
            hr_at_3 DOUBLE
        )
    """)
    for pipe in ["d_pipe", "g_pipe", "l_pipe"]:
        conn.execute(
            "INSERT INTO result_row VALUES (?, ?, ?, ?, ?, ?)",
            ["otel-001", variant, pipe, json.dumps(["svc-a", "svc-b"]), "normal", 1],
        )
    conn.close()


def test_fuse_smoke_flag_exits_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "results.duckdb"
    _create_minimal_result_db(db_path, "HELIOS-Full")
    result = subprocess.run(
        [sys.executable, "scripts/fuse_verdicts.py",
         "--db-path", str(db_path), "--smoke"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_fuse_produces_consensus_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "results.duckdb"
    _create_minimal_result_db(db_path, "HELIOS-Full")
    result = subprocess.run(
        [sys.executable, "scripts/fuse_verdicts.py", "--db-path", str(db_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    conn = duckdb.connect(str(db_path), read_only=True)
    count = conn.execute("SELECT COUNT(*) FROM consensus_verdict").fetchone()[0]
    conn.close()
    assert count >= 1


def test_fuse_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "results.duckdb"
    _create_minimal_result_db(db_path, "HELIOS-Full")
    for _ in range(2):
        subprocess.run(
            [sys.executable, "scripts/fuse_verdicts.py", "--db-path", str(db_path)],
            capture_output=True, text=True,
        )
    conn = duckdb.connect(str(db_path), read_only=True)
    count = conn.execute("SELECT COUNT(*) FROM consensus_verdict").fetchone()[0]
    conn.close()
    # Two runs must not duplicate rows (INSERT OR IGNORE semantics)
    assert count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/integration/test_fuse_verdicts.py -v
```

Expected: `FileNotFoundError` or test failure — `scripts/fuse_verdicts.py` does not exist.

- [ ] **Step 3: Create `scripts/fuse_verdicts.py`**

```python
#!/usr/bin/env python3
"""Idempotent fusion of pipeline rows → ConsensusVerdict rows.

Reads a merged DuckDB result file, applies UniformBordaConsensus per
(incident_id, variant) group, and writes ConsensusVerdict rows.
Idempotent: runs twice without duplicating rows (INSERT OR IGNORE).

Usage:
    python scripts/fuse_verdicts.py --db-path /tmp/helios-m4/helios_m4_results.duckdb
    python scripts/fuse_verdicts.py --db-path /tmp/helios-m4/helios_m4_results.duckdb --smoke
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_pipeline_rows(db_path: Path) -> dict[tuple[str, str], list[dict]]:
    import duckdb
    conn = duckdb.connect(str(db_path))
    _ensure_consensus_table(conn)

    rows = conn.execute(
        """
        SELECT incident_id, variant, pipeline, ranked_candidates, narrative
        FROM result_row
        WHERE narrative != 'gpipe-gated-or-skipped'
        ORDER BY incident_id, variant, pipeline
        """,
    ).fetchall()
    conn.close()

    groups: dict[tuple[str, str], list[dict]] = {}
    for incident_id, variant, pipeline, ranked_json, narrative in rows:
        key = (incident_id, variant)
        groups.setdefault(key, []).append({
            "pipeline": pipeline,
            "ranked_candidates": json.loads(ranked_json) if ranked_json else [],
            "narrative": narrative,
        })
    return groups


def _ensure_consensus_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consensus_verdict (
            incident_id              VARCHAR NOT NULL,
            variant                  VARCHAR NOT NULL,
            top_candidates           VARCHAR NOT NULL,
            borda_scores             VARCHAR NOT NULL,
            candidate_universe_size  INTEGER NOT NULL,
            consensus_rank           INTEGER NOT NULL,
            fusion_algorithm         VARCHAR NOT NULL,
            fusion_algorithm_sha     VARCHAR NOT NULL,
            cpr                      DOUBLE  NOT NULL DEFAULT 0,
            pipeline_row_count       INTEGER NOT NULL,
            run_id                   VARCHAR NOT NULL,
            timestamp_utc            VARCHAR NOT NULL,
            PRIMARY KEY (incident_id, variant)
        )
    """)


def _fuse_all(db_path: Path, run_id: str = "m4-fuse") -> int:
    from helios.consensus.uniform_borda import PassthroughConsensus, UniformBordaConsensus
    from helios.vcl import GatedComponentInactiveError, get_variant, set_current_manifest
    import duckdb

    groups = _load_pipeline_rows(db_path)
    borda = UniformBordaConsensus()
    passthrough = PassthroughConsensus()

    conn = duckdb.connect(str(db_path))
    fused_count = 0

    for (incident_id, variant), pipeline_rows in groups.items():
        manifest = get_variant(variant)
        set_current_manifest(manifest)

        try:
            cv = borda.fuse(
                incident_id=incident_id,
                variant=variant,
                pipeline_rows=pipeline_rows,
                run_id=run_id,
            )
        except GatedComponentInactiveError:
            cv = passthrough.fuse(
                incident_id=incident_id,
                variant=variant,
                pipeline_rows=pipeline_rows,
                run_id=run_id,
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO consensus_verdict
            (incident_id, variant, top_candidates, borda_scores, candidate_universe_size,
             consensus_rank, fusion_algorithm, fusion_algorithm_sha, cpr,
             pipeline_row_count, run_id, timestamp_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                cv.incident_id, cv.variant,
                json.dumps(cv.top_candidates),
                json.dumps(cv.borda_scores),
                cv.candidate_universe_size,
                cv.consensus_rank, cv.fusion_algorithm, cv.fusion_algorithm_sha,
                cv.cpr, cv.pipeline_row_count, cv.run_id, cv.timestamp_utc,
            ],
        )
        fused_count += 1

    conn.close()
    return fused_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fuse pipeline rows into ConsensusVerdict rows.")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true",
                        help="Validate DB has rows and consensus table exists; no fusion.")
    parser.add_argument("--run-id", default="m4-fuse")
    args = parser.parse_args(argv)

    if not args.db_path.exists():
        print(f"ERROR: DB not found: {args.db_path}", file=sys.stderr)
        return 1

    if args.smoke:
        import duckdb
        conn = duckdb.connect(str(args.db_path), read_only=True)
        try:
            count = conn.execute("SELECT COUNT(*) FROM result_row").fetchone()[0]
            print(f"Smoke: result_row count={count}")
        except Exception as exc:
            print(f"Smoke check failed: {exc}", file=sys.stderr)
            return 1
        finally:
            conn.close()
        return 0

    n = _fuse_all(args.db_path, run_id=args.run_id)
    print(f"Fused {n} (incident, variant) groups → ConsensusVerdict rows in {args.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/integration/test_fuse_verdicts.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Run full suite**

```bash
poetry run pytest --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add scripts/fuse_verdicts.py tests/integration/test_fuse_verdicts.py
git commit -m "feat(fuse): fuse_verdicts.py — idempotent Borda fusion with passthrough fallback"
```

---

### Task 11: analyse_results.py

**Files:**
- Create: `scripts/analyse_results.py`
- Test: `tests/test_analyse_results.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_analyse_results.py`:

```python
"""Unit tests for statistical analysis helpers."""
import math

import numpy as np
import pytest


def test_run_wilcoxon_detects_consistent_improvement() -> None:
    from scripts.analyse_results import run_wilcoxon
    # Full variant always beats noLLM by a consistent margin
    full_scores = [0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80]
    nollm_scores = [0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40]
    result = run_wilcoxon(full_scores, nollm_scores)
    assert result["n_nonzero"] > 0
    assert result["pvalue"] < 0.05
    assert "effect_r" in result


def test_run_wilcoxon_zero_variance_guard() -> None:
    from scripts.analyse_results import run_wilcoxon
    # 10 identical pairs — meets MIN_WILCOXON_PAIRS, hits zero_variance path
    identical = [0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60, 0.60]
    result = run_wilcoxon(identical, identical)
    assert result["zero_variance"] is True
    assert math.isnan(result["pvalue"])


def test_run_wilcoxon_insufficient_sample() -> None:
    from scripts.analyse_results import run_wilcoxon
    # 3 pairs — below MIN_WILCOXON_PAIRS; returns insufficient_sample flag
    result = run_wilcoxon([0.80, 0.60, 0.70], [0.40, 0.30, 0.20])
    assert result["insufficient_sample"] is True
    assert math.isnan(result["pvalue"])


def test_run_wilcoxon_returns_expected_keys() -> None:
    from scripts.analyse_results import run_wilcoxon
    # 10 pairs — meets floor, exercises full return path
    a = [0.80, 0.60, 0.70, 0.80, 0.60, 0.70, 0.80, 0.60, 0.70, 0.80]
    b = [0.40, 0.30, 0.20, 0.40, 0.30, 0.20, 0.40, 0.30, 0.20, 0.40]
    result = run_wilcoxon(a, b)
    for key in ("pvalue", "effect_r", "n_nonzero", "zero_variance", "insufficient_sample", "n_pairs"):
        assert key in result


def test_apply_holm_bonferroni_sorts_by_pvalue() -> None:
    from scripts.analyse_results import apply_holm_bonferroni
    pvalues = {"A-H3": 0.03, "A-H7": 0.01, "A-H1": 0.04}
    corrected = apply_holm_bonferroni(pvalues)
    assert set(corrected.keys()) == {"A-H3", "A-H7", "A-H1"}
    for k, v in corrected.items():
        assert "corrected_pvalue" in v
        assert "rejected" in v
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_analyse_results.py -v
```

Expected: `ModuleNotFoundError` — `scripts.analyse_results` not importable.

Note: to make scripts importable in tests, add `scripts/` to pytest `pythonpath` in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = [".", "scripts"]
```

Rerun after adding; confirm failure changes to `ImportError` (module exists but content missing).

- [ ] **Step 3: Create `scripts/analyse_results.py`**

```python
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


EXPLORATORY_ALPHA: float = 0.05


def run_wilcoxon(
    scores_a: list[float],
    scores_b: list[float],
) -> dict[str, Any]:
    from helios.config.m4_ablation import MIN_WILCOXON_PAIRS
    from scipy.stats import wilcoxon

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

    if n_nonzero == 0 or np.std(nonzero_diffs) == 0:
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

    # Rank-biserial r using n_nonzero
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

    # NaN pvalues (zero-variance) are excluded from correction
    valid_idx = [i for i, p in enumerate(raw) if not math.isnan(p)]
    valid_raw = [raw[i] for i in valid_idx]

    corrected_map: dict[int, tuple[bool, float]] = {}
    if valid_raw:
        rejected, corrected, _, _ = multipletests(valid_raw, method="holm", alpha=EXPLORATORY_ALPHA)
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
    """Load system-level (consensus) HR@3 for variant_a vs variant_b.

    Queries ``consensus_verdict.top_candidates`` — the fused system output —
    and computes HR@3 against ground truth.  This is the correct metric for
    hypothesis testing: a single-pipeline slice (e.g. d_pipe only) ignores
    the other two peer pipelines and does not reflect the multi-pipeline
    system's actual output.
    """
    import json
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

    def _to_hr(rows: list[tuple]) -> dict[str, float]:
        result: dict[str, float] = {}
        for incident_id, top_json in rows:
            if incident_id not in ground_truth:
                continue
            ranked: list[str] = json.loads(top_json) if isinstance(top_json, str) else list(top_json)
            result[incident_id] = float(hr_at_k(ranked, ground_truth[incident_id], k=3))
        return result

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
        print(f"ERROR: ground truth not found: {args.ground_truth_path}", file=sys.stderr)
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
                args.db_path, args.ground_truth_path, variant_a, variant_b,
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

    output = {
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_analyse_results.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Run full suite**

```bash
poetry run mypy
poetry run pytest --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add scripts/analyse_results.py tests/test_analyse_results.py pyproject.toml
git commit -m "feat(analysis): analyse_results.py — Wilcoxon + Holm-Bonferroni; power disclosure"
```

---

### Task 12: Replication script + replication doc

**Files:**
- Create: `scripts/replicate.py`
- Create: `docs/reproducibility/m4_replication.md`
- Test: `tests/integration/test_replicate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_replicate.py`:

```python
import subprocess
import sys
from pathlib import Path


def test_replicate_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/replicate.py", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--db-path" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/integration/test_replicate.py -v
```

Expected: fails — `scripts/replicate.py` does not exist.

- [ ] **Step 3: Create `scripts/replicate.py`**

```python
#!/usr/bin/env python3
"""10-percent replication check for Milestone 4 ablation results.

Reruns 2 incidents (max(1, NUM_INCIDENTS // 10)) through all variants
and verifies byte-equality of result_row entries against the target DB.

Usage:
    python scripts/replicate.py --db-path /tmp/helios-m4/helios_m4_results.duckdb \\
        --captures-dir data/captures --output data/replication_log.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from helios.config.m4_ablation import NUM_INCIDENTS
from helios.vcl import get_all_variants

_N_REPLICATE: int = max(1, NUM_INCIDENTS // 10)


def _select_replication_incidents(db_path: Path) -> list[str]:
    import duckdb
    conn = duckdb.connect(str(db_path), read_only=True)
    rows = conn.execute(
        "SELECT DISTINCT incident_id FROM result_row ORDER BY incident_id LIMIT ?",
        [_N_REPLICATE],
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replication check for M4 ablation results.")
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--captures-dir", type=Path, default=Path("data/captures"))
    parser.add_argument("--registry-path", type=Path, default=Path("data/snapshot_registry.jsonl"))
    parser.add_argument(
        "--reconciliation-path",
        type=Path, default=Path("data/reconciliation_ledger.jsonl"),
    )
    parser.add_argument("--exclusion-ledger", type=Path, default=Path("exclusion_ledger.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/replication_log.json"))
    args = parser.parse_args(argv)

    if not args.db_path.exists():
        print(f"ERROR: DB not found: {args.db_path}", file=sys.stderr)
        return 1

    incidents = _select_replication_incidents(args.db_path)
    if not incidents:
        print("ERROR: No incidents in DB to replicate", file=sys.stderr)
        return 1

    print(f"Replicating {len(incidents)} incidents: {incidents}")

    mismatches: list[dict] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        for variant_name in get_all_variants():
            rep_db = tmp_path / f"{variant_name}_rep.duckdb"
            proc = subprocess.run(
                [sys.executable, "scripts/run_one_variant.py",
                 "--variant", variant_name,
                 "--db-path", str(rep_db),
                 "--captures-dir", str(args.captures_dir),
                 "--registry-path", str(args.registry_path),
                 "--reconciliation-path", str(args.reconciliation_path),
                 "--exclusion-ledger", str(args.exclusion_ledger)],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                mismatches.append({"variant": variant_name, "error": proc.stderr})
                continue

            import duckdb
            orig_conn = duckdb.connect(str(args.db_path), read_only=True)
            rep_conn = duckdb.connect(str(rep_db), read_only=True)

            for inc_id in incidents:
                orig_rows = orig_conn.execute(
                    "SELECT * FROM result_row WHERE incident_id=? AND variant=? ORDER BY pipeline",
                    [inc_id, variant_name],
                ).fetchall()
                rep_rows = rep_conn.execute(
                    "SELECT * FROM result_row WHERE incident_id=? AND variant=? ORDER BY pipeline",
                    [inc_id, variant_name],
                ).fetchall()
                if orig_rows != rep_rows:
                    mismatches.append({
                        "variant": variant_name,
                        "incident_id": inc_id,
                        "mismatch": True,
                    })

            orig_conn.close()
            rep_conn.close()

    log = {
        "n_replicated": len(incidents),
        "incidents_replicated": incidents,
        "n_variants": len(get_all_variants()),
        "mismatches": mismatches,
        "passed": len(mismatches) == 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(log, indent=2), encoding="utf-8")
    if mismatches:
        print(f"REPLICATION FAILED: {len(mismatches)} mismatches. See {args.output}",
              file=sys.stderr)
        return 1
    print(f"Replication passed. Log at {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Create `docs/reproducibility/m4_replication.md`**

```markdown
# Milestone 4 Replication Log

**Purpose:** Record of the 10-percent byte-equality replication check per G3-8.
Generated by `scripts/replicate.py`.

## Protocol

- Replication sample: `max(1, NUM_INCIDENTS // 10)` incidents selected in incident_id order.
- All 8 variants re-run from frozen captures in `data/captures/`.
- Byte-equality check: `result_row` entries for replicated incidents must match original DB exactly.
- Acceptance criterion: zero mismatches.

## Results (populated after RES01 run)

| Date | Incidents replicated | Variants | Mismatches | Status | Log path |
|---|---|---|---|---|---|
| [PENDING: Stage 6 — post-run] | 2 | 8 | — | — | — |

## Chain of custody

- Original DB: `[PENDING: fill path post-run]`
- Replication DB: temporary (deleted after check)
- Script SHA: `[PENDING: fill from git log after run]`
```

- [ ] **Step 5: Create `docs/reproducibility/` directory (if absent)**

```bash
mkdir -p docs/reproducibility
```

- [ ] **Step 6: Run test to verify it passes**

```bash
poetry run pytest tests/integration/test_replicate.py -v
```

Expected: passes.

- [ ] **Step 7: Run full suite**

```bash
poetry run pytest --tb=short
```

- [ ] **Step 8: Commit**

```bash
git add scripts/replicate.py docs/reproducibility/m4_replication.md \
    tests/integration/test_replicate.py
git commit -m "feat(replicate): replicate.py 10-percent replication check; m4_replication.md"
```

---

### Task 13: Closeout — tracking rows DONE, ablation notebook L4, pre-push gate

**Files:**
- Modify: `docs/tracking/helios_mvp_tracking.md`
- Modify: `research/ablation_notebook.ipynb`
- Run: full pre-push gate

> **Note:** Steps 1–4 require the ablation run (RES01) and analysis (RES02) to have been executed. Complete those research tasks before running this closeout task.

- [ ] **Step 1: Transition M4 engineering rows to IN_PROGRESS then DONE**

For each of ENG01, ENG02, ENG03 in `docs/tracking/helios_mvp_tracking.md`:
1. First commit: set Status to `IN_PROGRESS`, set Started to today's date.
2. Second commit (after verification): set Status to `DONE`, set Done to today's date, set SHA to the relevant commit hash, set Ev_Type and Ev_Ref.

```bash
git add docs/tracking/helios_mvp_tracking.md
git commit -m "track(m4): mark ENG01/02/03 IN_PROGRESS"
# ... (implement and verify) ...
git add docs/tracking/helios_mvp_tracking.md
git commit -m "track(m4): mark ENG01/02/03 DONE (SHA: <commit>)"
```

- [ ] **Step 2: Execute RES01 — ablation run**

```bash
set -a; source .env; set +a
poetry run python scripts/run_ablation.py \
    --output-dir data/m4_runs \
    --captures-dir data/captures \
    --rollback-on-failure
```

Expected: `Ablation run complete. Results at data/m4_runs/helios_m4_results.duckdb`

Check row count:

```bash
poetry run python -c "
import duckdb
conn = duckdb.connect('data/m4_runs/helios_m4_results.duckdb', read_only=True)
print(conn.execute('SELECT COUNT(*) FROM result_row').fetchone()[0], 'pipeline rows')
conn.close()
"
```

Expected: 480 pipeline rows (or near it — exclusions reduce the count; check inclusion_rate >= 0.80).

- [ ] **Step 3: Execute fusion**

```bash
poetry run python scripts/fuse_verdicts.py \
    --db-path data/m4_runs/helios_m4_results.duckdb
```

Expected: `Fused N (incident, variant) groups → ConsensusVerdict rows`

- [ ] **Step 4: Execute RES02 — statistical analysis**

```bash
poetry run python scripts/analyse_results.py \
    --db-path data/m4_runs/helios_m4_results.duckdb \
    --output data/m4_results.json
```

Expected: `Results written to data/m4_results.json`

- [ ] **Step 5: Execute replication check**

```bash
set -a; source .env; set +a
poetry run python scripts/replicate.py \
    --db-path data/m4_runs/helios_m4_results.duckdb \
    --output data/replication_log.json
```

Expected: `Replication passed.`

- [ ] **Step 6: Populate m4_replication.md from replication_log.json**

Update `docs/reproducibility/m4_replication.md` results table with actual values from `data/replication_log.json`.

- [ ] **Step 7: Extend ablation_notebook.ipynb — L4 section**

Open `research/ablation_notebook.ipynb` and add an L4 section after L3. The L4 section must:

1. Load `data/m4_results.json`
2. Print a hypothesis-results table (hypothesis ID, comparison, raw p-value, Holm-corrected p-value, effect r, rejected/not)
3. Note: "These are exploratory results on the OTEL corpus. No binding inference is made."

Minimum cell structure:

```python
# Cell 1: Load results
import json
from pathlib import Path

results = json.loads(Path("data/m4_results.json").read_text())
print(f"Corpus: {results['corpus']}")
print(f"Type: {results['analysis_type']}")
print(f"Note: {results['note']}")
```

```python
# Cell 2: Print hypothesis table
hyps = results["hypotheses"]
print(f"{'Hyp':<8} {'Comparison':<40} {'raw p':>8} {'holm p':>8} {'r':>6} {'H0 rej':>7}")
print("-" * 80)
for hyp_id, data in hyps.items():
    praw = data.get("raw_pvalue", float("nan"))
    pcorr = data.get("corrected_pvalue", float("nan"))
    r = data.get("effect_r", float("nan"))
    rej = data.get("rejected", False)
    cmp = data.get("comparison", "—")
    print(f"{hyp_id:<8} {cmp:<40} {praw:>8.4f} {pcorr:>8.4f} {r:>6.3f} {str(rej):>7}")
```

```python
# Cell 3: Power disclosure
print("Power disclosure:")
print("  n=20 incidents; Wilcoxon exact two-sided; exploratory alpha=0.05")
print("  Effect sizes r < 0.3 are small; interpretive caution applies.")
print("  Confirmatory inference is reserved for Phase 2 (AIOpsLab corpus).")
```

- [ ] **Step 8: Run full pre-push gate**

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ && \
  poetry run ruff format --check helios/ scripts/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

Expected: all checks pass (exit 0). Fix any lint, type, test, or tracking failures before proceeding.

- [ ] **Step 9: Mark all M4 rows DONE in helios_mvp_tracking.md**

Update rows RES01, RES02, EVAL01, GATE01 to DONE with SHAs and evidence references.

- [ ] **Step 10: Final commit**

```bash
git add docs/tracking/helios_mvp_tracking.md \
    docs/reproducibility/m4_replication.md \
    research/ablation_notebook.ipynb \
    data/m4_results.json data/replication_log.json data/ground_truth.json
git commit -m "feat(m4): milestone 4 complete — ablation run, fusion, Wilcoxon, replication check, notebook L4"
```

---

## Exit criteria checklist

| Criterion | Verified by |
|---|---|
| UniformBorda implemented and property-tested | Task 6 + Task 7 tests pass |
| ConsensusVerdict schema frozen (schema-draft-v0.3) | Task 4 + Task 5 schema.sql |
| 480 pipeline rows present (or explained exclusions) | Task 13 Step 2 smoke check |
| Inclusion rate >= 0.80 | ResultStore.inclusion_rate() |
| Exclusion ledger populated | exclusion_ledger.jsonl entries |
| Fusion produces ConsensusVerdict rows | Task 10 integration test |
| Wilcoxon + Holm-Bonferroni results written | Task 13 Step 4 + data/m4_results.json |
| Replication check passed (zero mismatches) | Task 13 Step 5 replication_log.json |
| All M4 tracking rows DONE with SHA | Task 13 Step 9 |
| Pre-push gate passes | Task 13 Step 8 |
| Ablation notebook L4 section present | Task 13 Step 7 |
| Deviation log has 3 M4 entries | Task 1 Steps 4-6 |
