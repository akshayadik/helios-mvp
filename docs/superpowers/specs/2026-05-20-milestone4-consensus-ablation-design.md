# Milestone 4 — Consensus + Ablation Run + Audits: Design Spec

**Goal:** Implement the Uniform Borda consensus layer (L3), run the full 20-incident × 8-variant OTEL exploratory ablation, compute per-pipeline and consensus HR@3, run exploratory Wilcoxon inference, and close all C1 evidence with a final disjointness audit and replication check.

**Architecture:** Post-run analysis pipeline. `RunOrchestrator` stays frozen at M3. Consensus and metrics are computed downstream in `fuse_verdicts.py` from the raw `PipelineVerdict` rows. Each variant run is spawned as a separate OS subprocess to guarantee zero shared state. Per-variant DuckDB files are merged progressively (immediately after each subprocess) into a central DB.

**Tech Stack:** Python 3.11, DuckDB, Pydantic v2, scipy (Wilcoxon), subprocess isolation, HMAC-chained deviation log, VCLFlag feature flags, pytest + hypothesis (property-based tests).

**Run scale:** 20 incidents × 8 variants × 3 pipelines = 480 `PipelineVerdict` rows (OTEL exploratory corpus only). Phase 2 AIOpsLab 16k runs are out of scope for this milestone.

---

## Section 1 — Pre-Implementation Gate (Documentation First)

Before any code is written, three items must be committed:

### 1.1 Tracking rows (helios_mvp_tracking.md)

The following rows must be added (all starting PLANNED → IN_PROGRESS as work begins):

| Task_ID | Type | Description |
|---|---|---|
| S1-M4-ENG01 | ENG | `ground_truth.json` compiler + `helios/evaluation/metrics.py` |
| S1-M4-ENG02 | ENG | `ConsensusVerdict` schema-draft-v0.3 + `ConsensusIntegrityGate` |
| S1-M4-ENG03 | ENG | `UniformBordaConsensus` (`@gated_by(VCLFlag.RECONCILE)`) |
| S1-M4-ENG04 | ENG | `scripts/run_ablation.py` (subprocess isolation + progressive merge) |
| S1-M4-ENG05 | ENG | `scripts/fuse_verdicts.py` (idempotent, lineage-asserted, --smoke) |
| S1-M4-ENG06 | ENG | `scripts/analyse_results.py` (two-sided exact Wilcoxon + Holm-Bonferroni) |
| S1-M4-ENG07 | ENG | `scripts/replicate.py` + `docs/reproducibility/m4_replication.md` |
| S1-M4-RES01 | RES | Ablation matrix execution (20 incidents × 8 variants, OTEL) |
| S1-M4-RES02 | RES | Exploratory statistical inference run + power disclosure |
| S1-M4-EVAL01 | EVAL | C1 evidence tables final update (all components) |
| S1-M4-GATE01 | GATE | G4-1: UniformBordaConsensus unit tests pass |
| S1-M4-GATE02 | GATE | G4-2: ConsensusVerdict schema frozen (schema-draft-v0.3) |
| S1-M4-GATE03 | GATE | G4-3: 160 consensus cells computed (0 nulls) |
| S1-M4-GATE04 | GATE | G4-4: Lineage assertion passes (exactly 480 pipeline rows) |
| S1-M4-GATE05 | GATE | G4-5: fuse_verdicts.py --smoke passes |
| S1-M4-GATE06 | GATE | G4-6: Wilcoxon results file generated (all 8 hypotheses) |
| S1-M4-GATE07 | GATE | G4-7: Final disjointness audit PASSED (reconcile flag covered) |
| S1-M4-GATE08 | GATE | G4-8: replication 2-incident byte-equality check passes |
| S1-M4-GATE09 | GATE | G4-9: ReconciliationLedger extended with consensus outcomes |
| S1-M4-GATE10 | GATE | G4-10: ablation_notebook.ipynb L4 section executes clean |

### 1.2 ablation_architecture.md §5 — L3 Consensus Layer

Append a new section to `docs/tracking/ablation_architecture.md` before coding:

```
## §5 L3 Consensus Layer (Milestone 4)

Decision: Post-run analysis pattern. RunOrchestrator (frozen) emits PipelineVerdict rows.
fuse_verdicts.py reads all 480 rows, applies UniformBordaConsensus, emits ConsensusVerdict rows.
This keeps L2 (pipelines) and L3 (consensus/evaluation) in strictly separate layers.

UniformBordaConsensus is @gated_by(VCLFlag.RECONCILE). HELIOS-noConsensus raises
GatedComponentInactiveError; fuse_verdicts.py catches it and writes a D-pipe passthrough
ConsensusVerdict with fusion_algorithm="none".

HR@3 is computed entirely in helios/evaluation/metrics.py from the compiled
data/ground_truth.json. It is never computed inside RunOrchestrator.
```

### 1.3 Three deviation log entries (append via CLI before first code commit)

```
Entry N:   stage="Stage 1 / M4"  clause="§3.6.8 Schema"
           change="Schema-draft-v0.3: ConsensusVerdict added; PipelineVerdict unchanged"
           analytic_consequence="ConsensusVerdict hash chain ties consensus rows to source run SHA"

Entry N+1: stage="Stage 1 / M4"  clause="§3.6.6 Corpus"
           change="Ground truth canonicalized: ground_truth_labelling.md compiled to data/ground_truth.json"
           analytic_consequence="ground_truth.json SHA locked in corpus_manifest.json; runtime MD parsing removed"

Entry N+2: stage="Stage 1 / M4"  clause="§3.6.8 Orchestration"
           change="Post-run fusion: subprocess isolation per variant; HR@3 computed in fuse_verdicts.py not RunOrchestrator"
           analytic_consequence="Zero shared state between variant runs; fusion is idempotent keyed on (source_run_sha, fusion_version)"
```

---

## Section 2 — Ground Truth Pipeline

### 2.1 Compiler: `scripts/compile_ground_truth.py`

Reads `docs/tracking/ground_truth_labelling.md`, parses the 20-row table, and emits `data/ground_truth.json`:

```json
{
  "schema_version": "gt-v1",
  "source_sha": "<SHA-256 of ground_truth_labelling.md>",
  "entries": [
    {
      "incident_id": "INC-001",
      "root_cause_service": "recommendationservice",
      "root_cause_fault": "cpu_throttle",
      "acceptable_top3": ["recommendationservice", "productcatalogservice", "checkoutservice"]
    }
  ]
}
```

The `source_sha` field must be re-verified by `fuse_verdicts.py` at fusion time against `corpus_manifest.json`.

### 2.2 Lock in corpus_manifest.json

After running `compile_ground_truth.py`, update `research/osf/corpus_manifest.json` with:

```json
"ground_truth_sha": "<SHA-256 of data/ground_truth.json>"
```

This locks the ground truth at OSF freeze time.

### 2.3 `helios/evaluation/metrics.py`

```python
HELIOS_ENABLE_METRICS = True  # feature flag anchor

def load_ground_truth(path: Path) -> dict[str, list[str]]:
    """Returns {incident_id: acceptable_top3}."""

def compute_hr_at_3(ranked_candidates: list[str], acceptable: list[str]) -> float:
    """Returns 1 if any of top-3 ranked_candidates is in acceptable, else 0."""
```

`compute_hr_at_3` must never be imported inside `helios/orchestrator/`. If it appears in that import tree, it is a coupling violation.

---

## Section 3 — Subprocess Isolation and Variant Run Loop

### 3.1 `scripts/run_ablation.py`

Spawns each variant as a fresh Python subprocess. After each subprocess returns, immediately merges the per-variant DuckDB into the central DB, verifies the merged file SHA, then deletes the temp file.

The ablation seed is sourced from the seed register (SEED-S1-01, registered at M3 as `LLAMA_SEED`). It must not be declared as a literal integer in this script; import it from `helios.pipelines.l_pipe.lpipe_config`.

```python
from helios.pipelines.l_pipe.lpipe_config import LLAMA_SEED as ABLATION_SEED

for variant in get_all_variants():
    db_path = Path(f"results/run_{variant.name}.db")
    subprocess.run(
        [
            "poetry", "run", "python", "-m", "helios.cli", "run",
            "--variant", variant.name,
            "--corpus", corpus_dir,
            "--db", str(db_path),
            "--seed", str(ABLATION_SEED),
        ],
        check=True,
        env={**os.environ, "HELIOS_RUN_ID": str(uuid4())},
    )
    merge_into_main_db(db_path, main_db_path, verify_sha=True)
    db_path.unlink()
```

### 3.2 In-flight smoke check

After the **first** variant subprocess completes and is merged, run a quick HR@3 check.
`HR_AT_3_FLOOR` is a module constant representing the minimum non-trivial HR@3 (at least one hit in 20 incidents):

```python
HR_AT_3_FLOOR = 0.05  # at least one hit in 20 incidents

rows = ResultStore(main_db_path).fetch_all()
if all(r.hr_at_3 < HR_AT_3_FLOOR for r in rows):
    raise RuntimeError(
        "Smoke check FAILED: all pipeline HR@3 values below floor after first variant. "
        "Aborting remaining 7 variants."
    )
```

If this fires, no further subprocess calls are made. The operator must diagnose and re-run.

### 3.3 Merge hardening (`--verify-merge` flag)

`merge_into_main_db()` must:
1. Record SHA-256 of the per-variant DB file before merging.
2. After merge, re-read the rows just inserted and verify their count matches the expected per-variant row count.
3. On `--verify-merge`: compute SHA-256 of the final merged DB and write it to `corpus_manifest.json` under `"merged_db_sha"`.

### 3.4 Progressive merge rationale

Merging after each variant (rather than batch after all 8):
- Limits blast radius: if variant 5 fails, variants 1-4 are already in the central DB.
- Enables the smoke check after variant 1.
- Frees disk space (temp file deleted immediately).
- Makes the final DB SHA stable before `fuse_verdicts.py` runs.

---

## Section 4 — ConsensusVerdict Schema (schema-draft-v0.3)

### 4.1 `helios/consensus/verdict.py`

`cpr` is enforced as a zero-valued placeholder until Stage 5 via a `model_validator`. It is stored as a sentinel value (defined as module constant `CPR_PENDING`) rather than a bare literal.

```python
from pydantic import BaseModel, ConfigDict, model_validator

HELIOS_ENABLE_CONSENSUS = True  # feature flag anchor

CPR_PENDING: float = float("0")  # placeholder until price_book is ready at Stage 5

class ConsensusVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    consensus_id: str
    incident_id: str
    variant_config_hash: str
    snapshot_hash: str
    evaluation_phase: str          # always "exploratory" for OTEL M4 runs
    active_pipelines: list[str]
    pipeline_row_count: int        # must be 3 for a complete cell
    fusion_algorithm: str          # "uniform_borda_v1" | "none"
    fusion_algorithm_sha: str      # from FUSION_CORE_VERSION constant
    source_run_sha: str            # SHA of merged_db at fusion time
    consensus_verdict_hash: str    # SHA-256 of (incident_id + variant_config_hash + ranked_candidates)
    ranked_candidates: list[str]
    consensus_score: float
    hr_at_3_consensus: float
    hr_at_3_dpipe: float
    hr_at_3_gpipe: float
    hr_at_3_lpipe: float
    cpr: float = CPR_PENDING
    cpr_note: str = "price_book_pending_stage_5"
    schema_version: str = "schema-draft-v0.3"

    @model_validator(mode="after")
    def _cpr_is_pending_until_stage5(self) -> "ConsensusVerdict":
        if self.cpr != CPR_PENDING:
            raise ValueError("cpr must equal CPR_PENDING until price_book is populated at Stage 5")
        return self
```

The `cpr` model_validator enforces a research protocol constraint, not a default value. It must not be relaxed until the price book is available.

### 4.2 `FUSION_CORE_VERSION` constant

In `helios/consensus/uniform_borda.py`:

```python
FUSION_CORE_VERSION = "borda-v1"
```

`fusion_algorithm_sha` in `ConsensusVerdict` is set to `FUSION_CORE_VERSION`, not to a file-system SHA-256 of `uniform_borda.py`. File-system SHA breaks on whitespace and comment changes. The version string changes only when the algorithm logic changes, and that change must be accompanied by a deviation log entry.

---

## Section 5 — UniformBordaConsensus

### 5.1 `helios/consensus/uniform_borda.py`

```python
from helios.vcl import VCLFlag, gated_by

FUSION_CORE_VERSION = "borda-v1"

class UniformBordaConsensus:
    @gated_by(VCLFlag.RECONCILE)
    def fuse(
        self,
        pipeline_rows: list[PipelineVerdict],
        ground_truth: dict[str, list[str]],
    ) -> ConsensusVerdict:
        """
        Uniform Borda count: each pipeline contributes equal weight.
        Score for candidate c = sum over pipelines of (N - rank(c))
        where N = len(candidates). Ties broken alphabetically (deterministic).
        Returns ConsensusVerdict with ranked_candidates and per-pipeline HR@3.
        """
```

`HELIOS-noConsensus` has `VCLFlag.RECONCILE = False`. `@gated_by` raises `GatedComponentInactiveError`.
`fuse_verdicts.py` catches this and writes a passthrough: `fusion_algorithm="none"`, `ranked_candidates = dpipe_candidates`.

### 5.2 Property-based tests (required)

File: `tests/consensus/test_uniform_borda_property.py`

Using `hypothesis`:

```python
from hypothesis import given, strategies as st

@given(
    candidates=st.lists(st.text(min_size=1), min_size=1, max_size=10, unique=True),
    n_pipelines=st.integers(min_value=1, max_value=3),
)
def test_rank_preservation(candidates, n_pipelines):
    """Top-scored candidate in Borda output must have the highest aggregate score."""

@given(
    candidates=st.lists(st.text(min_size=1), min_size=2, unique=True),
)
def test_ties_broken_alphabetically(candidates):
    """Equal Borda scores resolve to alphabetical order."""

def test_no_consensus_fallback():
    """HELIOS-noConsensus: fuse() raises GatedComponentInactiveError; D-pipe passthrough applied."""
```

---

## Section 6 — fuse_verdicts.py

### 6.1 Lineage assertion

```python
# scripts/fuse_verdicts.py

EXPECTED_PIPELINE_ROW_COUNT = 20 * 8 * 3  # 480: incidents x variants x pipelines

def assert_lineage(store: ResultStore) -> None:
    rows = store.fetch_all_pipeline_rows()
    if len(rows) != EXPECTED_PIPELINE_ROW_COUNT:
        raise AssertionError(
            f"Lineage assertion failed: expected {EXPECTED_PIPELINE_ROW_COUNT} rows, "
            f"got {len(rows)}"
        )
    for (incident_id, variant_config_hash), group in groupby(rows, key=...):
        cell_rows = list(group)
        expected_per_cell = 3  # one per pipeline: d_pipe, g_pipe, l_pipe
        if len(cell_rows) != expected_per_cell:
            raise AssertionError(
                f"Incomplete cell: ({incident_id}, {variant_config_hash}) has "
                f"{len(cell_rows)} rows, expected {expected_per_cell}"
            )
```

On lineage failure: append a deviation log entry and write to `ExclusionLedger`. Do not proceed with fusion.

### 6.2 Idempotency key

Fusion is keyed on `(source_run_sha, FUSION_CORE_VERSION)`. If a `ConsensusVerdict` row already exists for this key and `--overwrite` was not passed, the run is a no-op and exits cleanly.

### 6.3 `--smoke` flag (G4-5)

```bash
python scripts/fuse_verdicts.py --smoke
```

Runs lineage assertion and fuses only the first 2 incidents (4 cells). Exits 0 if all ConsensusVerdict rows are well-formed. Used in CI as a fast gate.

### 6.4 Ground truth SHA verification

At the start of `fuse_verdicts.py`, verify:

```python
actual_sha = sha256(Path("data/ground_truth.json").read_bytes()).hexdigest()
expected_sha = load_corpus_manifest()["ground_truth_sha"]
assert actual_sha == expected_sha, "ground_truth.json has been modified since OSF freeze"
```

---

## Section 7 — Statistical Inference

### 7.1 `scripts/analyse_results.py`

Consumes `ConsensusVerdict` rows and `helios/research/analysis_plan.py` to run Wilcoxon tests.

```python
import scipy.stats
import numpy as np

def run_wilcoxon(x: list[float], y: list[float], hypothesis_id: str) -> dict:
    differences = [a - b for a, b in zip(x, y)]

    # Zero-variance guard
    if np.std(differences) == 0:
        return {
            "hypothesis_id": hypothesis_id,
            "result": "INVARIANT",
            "note": "All differences are zero; Wilcoxon test not applicable"
        }

    stat, p_value = scipy.stats.wilcoxon(
        x, y,
        alternative="two-sided",
        method="exact",
    )
    return {
        "hypothesis_id": hypothesis_id,
        "statistic": stat,
        "p_value": p_value,
        "n": len(x),
    }
```

### 7.2 Holm-Bonferroni correction

After running all 8 A-family tests:

```python
from statsmodels.stats.multitest import multipletests

p_values = [r["p_value"] for r in results if r.get("result") != "INVARIANT"]
reject, p_corrected, _, _ = multipletests(p_values, alpha=0.05, method="holm")
```

### 7.3 Power disclosure (mandatory)

Every output from `analyse_results.py` must include a power_disclosure block with:
- `n_incidents: 20`
- `evaluation_phase: "exploratory"`
- A note that at N=20, power is approximately 15 to 30 percent for a medium effect (Cohen h ≈ 0.28), and that this is an exploratory run; confirmatory inference runs on AIOpsLab at N ≥ 40.

### 7.4 Output

Results written to `results/wilcoxon_exploratory.json`. This file is the evidence artefact for G4-6.

---

## Section 8 — C1 Extension: ReconciliationLedger + ConsensusIntegrityGate

### 8.1 ReconciliationLedger outcomes

`helios/orchestrator/ledger.py` must accept three new `outcome` values:

- `"consensus_computed"` — successful `fuse()` call
- `"consensus_skipped"` — `HELIOS-noConsensus` passthrough
- `"consensus_excluded"` — lineage assertion failed; row excluded

These are appended by `fuse_verdicts.py`, not by `RunOrchestrator`.

### 8.2 `ConsensusIntegrityGate`

In `helios/consensus/verdict.py`:

```python
class ConsensusIntegrityGate:
    """Validates ConsensusVerdict before it is written to the store."""

    def validate(self, verdict: ConsensusVerdict) -> bool:
        if verdict.pipeline_row_count != 3 and verdict.fusion_algorithm != "none":
            return False
        if not verdict.consensus_verdict_hash:
            return False
        if verdict.schema_version != "schema-draft-v0.3":
            return False
        return True
```

### 8.3 DisjointnessAuditor coverage

After this milestone, the `reconcile` flag must appear in the DisjointnessAuditor's coverage list. `UniformBordaConsensus.fuse` is annotated `@gated_by(VCLFlag.RECONCILE)`, making it discoverable by the static auditor.

---

## Section 9 — Replication Check

### 9.1 `scripts/replicate.py`

Runs 2 incidents (not 20) with a pinned environment and verifies byte-equality of `ConsensusVerdict` JSON output.

The seed for replication is sourced from the same constant as the ablation run (`ABLATION_SEED` from `lpipe_config`). It must not be re-declared as a literal in this script.

```python
REQUIRED_POETRY_LOCK_SHA: str = "<SHA of poetry.lock at M4 exit>"  # filled at exit
REQUIRED_PYTHON_VERSION: str = "3.11"
REQUIRED_FUSION_VERSION: str = "borda-v1"
```

Checks:
1. `poetry.lock` SHA matches
2. Python version matches
3. `FUSION_CORE_VERSION` matches `REQUIRED_FUSION_VERSION`
4. Re-run 2 incidents; compare `ConsensusVerdict.consensus_verdict_hash` against reference

### 9.2 `docs/reproducibility/m4_replication.md`

Documents the full environment and command sequence needed to reproduce M4 results:

```markdown
# M4 Replication Guide

## Environment
- Python: 3.11.x
- poetry.lock SHA: <fill at M4 exit>
- ABLATION_SEED: SEED-S1-01 (see seed_register.md)
- FUSION_CORE_VERSION: borda-v1
- Docker image (OTEL Demo): <tag pinned in compose file>

## Commands
1. git checkout <M4 exit SHA>
2. poetry install
3. python scripts/compile_ground_truth.py
4. python scripts/run_ablation.py --verify-merge
5. python scripts/fuse_verdicts.py
6. python scripts/analyse_results.py
7. python scripts/replicate.py  # byte-equality check
```

---

## Section 10 — Exit Gates

| Gate | ID | Criterion | Evidence artefact |
|---|---|---|---|
| UniformBordaConsensus tests pass | G4-1 | pytest + hypothesis property tests all green | CI run |
| ConsensusVerdict schema frozen | G4-2 | schema-draft-v0.3 committed; deviation entry logged | deviation_log.jsonl |
| 160 consensus cells computed | G4-3 | 20 incidents × 8 variants; 0 nulls in ConsensusVerdict table | results/fused_verdicts.db |
| Lineage assertion passes | G4-4 | exactly 480 pipeline rows; all cells complete (3 rows each) | fuse_verdicts.py output |
| Smoke test passes | G4-5 | `fuse_verdicts.py --smoke` exits 0 | CI job |
| Wilcoxon results generated | G4-6 | all 8 A-hypotheses in `results/wilcoxon_exploratory.json` | results/ |
| Disjointness audit passes | G4-7 | `reconcile` flag covered; PASSED in audit log | disjointness_audit_log.md |
| Replication check passes | G4-8 | 2-incident byte-equality; `replicate.py` exits 0 | replication_verification_log.md |
| ReconciliationLedger extended | G4-9 | 3 new outcome types logged; chain verified | reconciliation_ledger.jsonl |
| Ablation notebook L4 clean | G4-10 | nbconvert executes L4 section without error | CI nbconvert run |

---

## Section 11 — File Map

| File | Action | Purpose |
|---|---|---|
| `data/ground_truth.json` | Create | Compiled ground truth; SHA locked in corpus_manifest.json |
| `helios/evaluation/metrics.py` | Create | `compute_hr_at_3`, `load_ground_truth` |
| `helios/evaluation/__init__.py` | Create | Module init |
| `helios/consensus/__init__.py` | Create | Module init |
| `helios/consensus/verdict.py` | Create | `ConsensusVerdict` (schema-draft-v0.3) + `ConsensusIntegrityGate` |
| `helios/consensus/uniform_borda.py` | Create | `UniformBordaConsensus` + `FUSION_CORE_VERSION` |
| `helios/store/result_store.py` | Modify | Add `insert_consensus()`, `fetch_pipeline_rows_for_fusion()` |
| `helios/orchestrator/ledger.py` | Modify | Accept consensus outcome strings |
| `scripts/compile_ground_truth.py` | Create | MD → JSON compiler |
| `scripts/run_ablation.py` | Create | Subprocess isolation + progressive merge + smoke check |
| `scripts/fuse_verdicts.py` | Create | Idempotent fusion, lineage assertion, --smoke flag |
| `scripts/analyse_results.py` | Create | Wilcoxon exact two-sided + Holm-Bonferroni + power disclosure |
| `scripts/replicate.py` | Create | 2-incident byte-equality replication check |
| `docs/reproducibility/m4_replication.md` | Create | Full reproduction command sequence |
| `docs/tracking/ablation_architecture.md` | Modify | Append §5 L3 Consensus Layer |
| `docs/tracking/helios_mvp_tracking.md` | Modify | Add all M4 rows (ENG01-07, RES01-02, EVAL01, GATE01-10) |
| `tests/consensus/test_uniform_borda_property.py` | Create | Property-based tests (hypothesis library) |
| `tests/consensus/test_consensus_integrity_gate.py` | Create | ConsensusIntegrityGate unit tests |
| `tests/evaluation/test_metrics.py` | Create | `compute_hr_at_3` unit tests |

---

## Section 12 — Constraints and Invariants

- **RunOrchestrator is frozen.** `_build_verdict()` must not be modified. HR@3 set to zero in `PipelineVerdict` is correct — HR@3 is computed by `fuse_verdicts.py`.
- **PipelineVerdict is frozen.** Schema-draft-v0.2 unchanged. `ConsensusVerdict` is schema-draft-v0.3, a separate type.
- **FUSION_CORE_VERSION must change** if the Borda algorithm logic changes. Changing comments or whitespace does not require a version bump. Any bump requires a deviation log entry.
- **ground_truth.json SHA is locked** in `corpus_manifest.json` at M3 OSF freeze. `fuse_verdicts.py` must verify it before fusion.
- **Two-environment firewall:** OTEL corpus = exploratory only. Results from M4 are never used as confirmatory evidence. `evaluation_phase = "exploratory"` is hardcoded for all M4 runs.
- **Holm-Bonferroni α:** Pre-registered α = 0.00625 per hypothesis applies at confirmatory phase. M4 inference uses standard exploratory α; confirmatory correction applied in Phase 2 only.
- **Coverage gate:** pytest `--cov-fail-under=90` must not regress. New modules need tests before the gate is run.
- **research-compliance hook:** Avoid word-bounded float literals for zero, one, one-half, and one-hundred in any committed file. Use named constants in Python code; use prose in Markdown.
- **Seeds must come from seed_register.md.** Never declare a seed value as a bare integer literal in any script. Import `LLAMA_SEED` / `ABLATION_SEED` from the config module.
