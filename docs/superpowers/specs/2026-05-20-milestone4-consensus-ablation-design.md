# Milestone 4 — Consensus + Ablation Run + Audits: Design Spec

**Goal:** Implement the Uniform Borda consensus layer (L3), run the full 20-incident × 8-variant OTEL exploratory ablation, compute per-pipeline and consensus HR@3, run exploratory Wilcoxon inference, and close all C1 evidence with a final disjointness audit and replication check.

**Architecture:** Post-run analysis pipeline. `RunOrchestrator` stays frozen at M3. Consensus and metrics are computed downstream in `fuse_verdicts.py` from the raw `PipelineVerdict` rows. Each variant run is spawned as a separate OS subprocess to guarantee zero shared state. Per-variant DuckDB files are collected individually, then merged atomically in a single transaction after all subprocesses succeed, with a pre-merge backup and `--rollback-on-failure` recovery path.

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
| S1-M4-ENG04 | ENG | `scripts/run_ablation.py` (subprocess isolation + atomic merge + rollback) |
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

This anchors the ground truth at OSF freeze time. The SHA is an integrity check, not permanent immutability.

### 2.2a Ground truth label correction path (fix #6)

If a label correction is required after the SHA is locked (e.g., a service name typo), the correction path is:

```bash
# 1. Fix the error in ground_truth_labelling.md
# 2. Recompile
python scripts/compile_ground_truth.py

# 3. Log the correction as a deviation entry (required for DSR validity)
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M4" \
  --clause "§3.6.6 Corpus" \
  --change "Ground truth label correction: <service_name> typo fixed in INC-XXX" \
  --reason "<describe the error and its source>" \
  --analytic-consequence "ground_truth_sha in corpus_manifest.json updated; prior analysis runs using old SHA are invalidated"

# 4. Regenerate the OSF manifest to update ground_truth_sha
poetry run python bin/verify_osf_freeze.py --generate
```

`compile_ground_truth.py` must support a `--update-manifest` flag that performs steps 1-4 atomically: recompile → write new SHA to `corpus_manifest.json`. It must refuse to run if no deviation log entry exists for the current git HEAD (checked by calling `bin/log_deviation.py verify`). This prevents silent SHA updates.

### 2.3 `helios/evaluation/metrics.py`

```python
HELIOS_ENABLE_METRICS = True  # feature flag anchor

def load_ground_truth(path: Path) -> dict[str, list[str]]:
    """Returns {incident_id: acceptable_top3}."""

def compute_hr_at_3(ranked_candidates: list[str], acceptable: list[str]) -> float:
    """Returns 1 if any of top-3 ranked_candidates is in acceptable, else 0."""
```

`compute_hr_at_3` must never be imported inside `helios/orchestrator/`. If it appears in that import tree, it is a coupling violation.

### 2.4 `helios/config/m4_ablation.py`

All magic numbers, expected counts, and floor values are centralised here. Every script imports from this module rather than declaring literals inline.

```python
from helios.vcl.variants import get_all_variants

# Corpus dimensions — computed, not hardcoded
NUM_INCIDENTS: int = 20
NUM_PIPELINES: int = 3  # d_pipe, g_pipe, l_pipe
NUM_VARIANTS: int = len(get_all_variants())
EXPECTED_PIPELINE_ROW_COUNT: int = NUM_INCIDENTS * NUM_VARIANTS * NUM_PIPELINES

# Quality floors
HR_AT_3_FLOOR: float = 0.05   # minimum non-trivial HR@3 (≥1 hit in 20 incidents)

# L-pipe sampling
LPIPE_SAMPLES_DEFAULT: int = 1
LPIPE_SAMPLES_REPLICATION: int = 3

# Output paths
ABLATION_DB_PATH: str = "results/m4_pipeline_verdicts.duckdb"
MANIFEST_PATH: str = "results/m4_variant_manifest.json"
ANALYSIS_OUTPUT_PATH: str = "results/m4_exploratory_analysis.json"
```

`NUM_VARIANTS` is computed at import time from `get_all_variants()` so that adding a variant automatically updates `EXPECTED_PIPELINE_ROW_COUNT` without a manual constant change.

---

## Section 3 — Subprocess Isolation and Atomic Merge

### 3.1 `scripts/run_ablation.py` — subprocess loop

All eight variants run first; the central DB is not touched until all succeed. Each subprocess writes to an isolated per-variant file. After each subprocess returns, the file is integrity-checked and its SHA-256 is recorded in `MANIFEST_PATH`. No merge occurs in this phase.

The ablation seed is sourced from SEED-S1-01 (`LLAMA_SEED`). It must not be declared as a literal integer; import it from `helios.pipelines.l_pipe.lpipe_config`.

```python
from helios.config.m4_ablation import ABLATION_DB_PATH, MANIFEST_PATH
from helios.pipelines.l_pipe.lpipe_config import LLAMA_SEED as ABLATION_SEED

manifest: dict[str, str] = {}  # variant_name → per-variant DB SHA

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
    _check_db_integrity(db_path)          # row-count probe (see 3.2)
    manifest[variant.name] = sha256(db_path.read_bytes()).hexdigest()
    _run_smoke_check_if_first(variant, db_path)  # see 3.3

Path(MANIFEST_PATH).write_text(json.dumps(manifest, indent=2))
_atomic_merge(manifest, Path(ABLATION_DB_PATH), rollback=args.rollback_on_failure)
```

### 3.2 Per-variant integrity check

`_check_db_integrity(db_path: Path) -> None` opens the file in read-only mode and runs a row-count query against the `pipeline_verdicts` table. DuckDB does not support SQLite's `PRAGMA integrity_check`; a successful read-only row-count query is the correct equivalent. If the connection or query raises, the function raises `RuntimeError` with the variant name. The ablation loop halts; no SHA is written to the manifest.

### 3.3 In-flight smoke check (first variant only)

`_run_smoke_check_if_first(variant, db_path)` fires only when `variant` is the first in `get_all_variants()`. It reads the per-variant DB **directly** (not the central DB, which has not been touched yet), computes HR@3 against `data/ground_truth.json`, and aborts if all rows are below `HR_AT_3_FLOOR`:

```python
from helios.config.m4_ablation import HR_AT_3_FLOOR

rows = ResultStore(db_path).fetch_all()
if all(r.hr_at_3 < HR_AT_3_FLOOR for r in rows):
    subprocess.run(
        [
            "poetry", "run", "python", "bin/log_deviation.py",
            "--stage", "Stage 1 / M4",
            "--clause", "§3.6.8 Orchestration",
            "--change", "Smoke check abort: HR@3 below floor after first variant",
            "--reason", (
                f"All {len(rows)} pipeline rows have HR@3 < {HR_AT_3_FLOOR}; "
                "likely ground_truth.json mismatch or corpus path mapping error"
            ),
            "--analytic-consequence", "Ablation run aborted; no variant DBs merged",
        ],
        check=True,
    )
    raise RuntimeError(
        "Smoke check FAILED. Deviation logged. Remaining 7 variants not executed."
    )
```

### 3.4 Atomic merge with rollback (`_atomic_merge`)

After all 8 variant DBs are written and the manifest is saved, merge into the central DB:

```python
def _atomic_merge(
    manifest: dict[str, str],
    central_db: Path,
    rollback: bool = True,
) -> None:
    backup = central_db.with_suffix(".duckdb.bak")
    if central_db.exists() and rollback:
        shutil.copy2(central_db, backup)
    try:
        con = duckdb.connect(str(central_db))
        for variant_name, expected_sha in manifest.items():
            db_path = Path(f"results/run_{variant_name}.db")
            actual_sha = sha256(db_path.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                raise RuntimeError(
                    f"SHA mismatch for {variant_name}: manifest={expected_sha[:12]} "
                    f"actual={actual_sha[:12]}"
                )
            con.execute(f"ATTACH '{db_path}' AS v")
            con.execute("BEGIN")
            con.execute(
                "INSERT INTO pipeline_verdicts SELECT * FROM v.pipeline_verdicts"
            )
            con.execute("COMMIT")
            con.execute("DETACH v")
            db_path.unlink()
        # Record final merged DB SHA
        con.close()
        merged_sha = sha256(central_db.read_bytes()).hexdigest()
        _update_corpus_manifest(merged_db_sha=merged_sha)
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        if rollback and backup.exists():
            shutil.move(str(backup), str(central_db))
        raise
    finally:
        if backup.exists():
            backup.unlink(missing_ok=True)
```

SHA re-verification at merge time (comparing against `MANIFEST_PATH` values) detects any file-system mutation between subprocess exit and final merge.

### 3.5 Merge design rationale

Single final merge was chosen over progressive merge for this milestone because:
- Atomicity: all-or-nothing semantics; partial merges are not possible.
- Rollback: if any variant's SHA mismatches or the ATTACH fails, the central DB is restored from backup.
- Audit: the manifest file records per-variant SHAs before the merge, creating a tamper-evident chain from subprocess → manifest → central DB SHA in `corpus_manifest.json`.

Trade-off accepted: blast radius is larger than progressive merge (a subprocess failure in variant 7 means variants 1-6 are still on disk but not yet merged). Mitigated by: (a) per-variant DB files are retained until the merge succeeds, and (b) the manifest records SHAs so a partial re-run can be detected.

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
    fusion_algorithm_sha: str      # AST-based semantic hash of uniform_borda.py (see Section 4.2)
    source_run_sha: str            # SHA of merged_db at fusion time
    consensus_verdict_hash: str    # SHA-256 of (incident_id + variant_config_hash + ranked_candidates_json)
    ranked_candidates: list[str]   # stored as VARCHAR[] in DuckDB (see Section 4.3)
    # Fused result only — no per-pipeline HR@3 duplication
    consensus_score: float
    hr_at_3_consensus: float

    # Reference keys for tracing back to source PipelineVerdict rows
    # Format: "<run_id>|<pipeline>" for each of the 3 pipeline verdicts fused
    source_pipeline_verdict_keys: list[str]

    # L-pipe variance fields (populated when --lpipe-samples > 1)
    lpipe_hr_at_3_samples: list[float]    # length == LPIPE_SAMPLES used; [hr] when default
    lpipe_sample_count: int               # 1 by default; 3 for replication mode

    cpr: float = CPR_PENDING
    cpr_note: str = "price_book_pending_stage_5"
    schema_version: str = "schema-draft-v0.3"

    @model_validator(mode="after")
    def _cpr_is_pending_until_stage5(self) -> "ConsensusVerdict":
        # Stage 5 guard: CpR requires price_book.md to be populated (Stage 5 freeze).
        # This validator must not be relaxed before then.
        if self.cpr != CPR_PENDING:
            raise ValueError("cpr must equal CPR_PENDING until price_book is populated at Stage 5")
        return self
```

**Per-pipeline HR@3 removal rationale:** `hr_at_3_dpipe`, `hr_at_3_gpipe`, `hr_at_3_lpipe` are removed from `ConsensusVerdict`. They would duplicate data already present in `PipelineVerdict` rows. `analyse_results.py` computes per-pipeline HR@3 on demand by joining `ConsensusVerdict` with `PipelineVerdict` on `(incident_id, variant_config_hash)`. This keeps the schema normalised.

**`source_pipeline_verdict_keys`** stores `"<run_id>|<pipeline>"` for each of the 3 fused rows, allowing `fuse_verdicts.py` to be audited post-hoc without re-reading the full DB.

### 4.2 AST-based semantic fingerprint

`fusion_algorithm_sha` in `ConsensusVerdict` is populated from `FUSION_ALGORITHM_SHA`, a module-level constant computed by parsing `uniform_borda.py`'s own AST at import time. This is stable across whitespace and comment edits; it changes only when functional logic changes.

In `helios/consensus/uniform_borda.py`:

```python
import ast
import hashlib
from pathlib import Path

def _compute_ast_hash() -> str:
    """Hash functional content of this module, stripping docstrings and comments."""
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    # Strip leading docstrings from all compound nodes
    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module),
        ):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body.pop(0)
    canonical = ast.dump(tree, indent=None)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


FUSION_CORE_VERSION = "borda-v1"   # human-readable; update when algorithm changes
FUSION_ALGORITHM_SHA = _compute_ast_hash()  # tamper-evident; auto-updates on logic change
```

`FUSION_ALGORITHM_SHA` is recorded in every `ConsensusVerdict` row. Re-running `fuse_verdicts.py` after a logic change produces a different SHA, making any mid-run code change detectable in the output artefacts.

`FUSION_CORE_VERSION` is used for the idempotency key (Section 6.2) and for the `fusion_algorithm` field. Both are required; one is human-readable, the other is tamper-evident.

### 4.3 DuckDB LIST column insertion (fix for array casting mismatch)

DuckDB's parameter binding does not accept Python `list[str]` directly as a `VARCHAR[]` column value; passing a list via `?` placeholder may be interpreted as multi-row input or serialised as a string blob depending on the DuckDB-Python driver version.

The storage layer must not hand-serialize individual fields. Use Pydantic's `model_dump()` to get a dict, then apply `::VARCHAR[]` casts for list columns. This keeps serialisation owned by the model, not scattered across the storage layer:

```python
import json, duckdb

def insert_consensus_verdict(con: duckdb.DuckDBPyConnection, cv: ConsensusVerdict) -> None:
    d = cv.model_dump()
    con.execute(
        """
        INSERT INTO consensus_verdicts VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?::VARCHAR[],   -- ranked_candidates
            ?::VARCHAR[],   -- active_pipelines
            ?::VARCHAR[],   -- source_pipeline_verdict_keys
            ?::DOUBLE[],    -- lpipe_hr_at_3_samples
            ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            d["consensus_id"], d["incident_id"], d["variant_config_hash"],
            d["snapshot_hash"], d["evaluation_phase"], d["pipeline_row_count"],
            d["fusion_algorithm"],
            json.dumps(d["ranked_candidates"]),              # -> ::VARCHAR[]
            json.dumps(d["active_pipelines"]),               # -> ::VARCHAR[]
            json.dumps(d["source_pipeline_verdict_keys"]),   # -> ::VARCHAR[]
            json.dumps(d["lpipe_hr_at_3_samples"]),          # -> ::DOUBLE[]
            d["lpipe_sample_count"], d["consensus_score"], d["hr_at_3_consensus"],
            d["fusion_algorithm_sha"], d["source_run_sha"], d["consensus_verdict_hash"],
            d["cpr"], d["schema_version"],
        ],
    )
```

`model_dump()` ensures field aliases, validators, and type coercions defined in `ConsensusVerdict` are respected before the dict reaches the storage layer. If the schema gains or loses a field, the storage layer does not need to change — only the INSERT column list changes.

The same explicit cast must be used when writing `PipelineVerdict.ranked_candidates` to DuckDB in `ResultStore`. A unit test must verify round-trip: insert a ConsensusVerdict, fetch it, reconstruct via `ConsensusVerdict.model_validate(row_dict)`, assert equality.

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
        Score for candidate c = sum over pipelines of (N - rank(c, pipeline_ranking))
        where N = len(candidates for that pipeline).
        Final sort key: (-borda_score, candidate_name). This is a stable composite key
        that produces identical results regardless of Python dict insertion order or
        Timsort's internal positioning of equal-score elements.
        """
```

**Tie-breaking contract (fix #1):** The sort must use `sorted(candidates, key=lambda c: (-scores[c], c))`. Using `-score` descending and `candidate_name` ascending as a tiebreaker guarantees byte-lexicographic determinism across all variants and seeds. Tests must verify: (a) two candidates with equal scores always resolve to alphabetical order, and (b) the property holds when input candidates are given in reverse-alphabetical order.

**Layer boundary contract (fix #4):** `UniformBordaConsensus.fuse()` implements ONLY the Borda algorithm. It has no knowledge of D-pipe, fallback rankings, or what to do when `VCLFlag.RECONCILE = False`. `@gated_by` raises `GatedComponentInactiveError`; the coordinator (`fuse_verdicts.py`) is solely responsible for catching it.

The null-transform is encapsulated in a separate `PassthroughConsensus` class in `helios/consensus/uniform_borda.py`:

```python
class PassthroughConsensus:
    """Null-transform consensus: emits D-pipe rankings unchanged. Used when RECONCILE=False."""

    def fuse(
        self,
        pipeline_rows: list[PipelineVerdict],
        ground_truth: dict[str, list[str]],
    ) -> ConsensusVerdict:
        dpipe_row = next(r for r in pipeline_rows if r.pipeline == "d_pipe")
        return ConsensusVerdict(
            # ... all required fields, with:
            fusion_algorithm="none",
            ranked_candidates=dpipe_row.ranked_candidates,
            source_pipeline_verdict_keys=[
                f"{dpipe_row.run_id}|d_pipe"
            ],
            lpipe_hr_at_3_samples=[],
            lpipe_sample_count=0,
            # ... etc.
        )
```

`fuse_verdicts.py` selects the strategy at the cell level:

```python
try:
    verdict = UniformBordaConsensus().fuse(pipeline_rows, ground_truth)
except GatedComponentInactiveError:
    verdict = PassthroughConsensus().fuse(pipeline_rows, ground_truth)
```

This keeps `UniformBordaConsensus` free of VCL state knowledge, and `PassthroughConsensus` is independently testable. Both implement the same `fuse()` interface — no isinstance checks, no conditionals in the coordinator beyond the single try/except.

### 5.3 `--lpipe-samples` flag

`run_ablation.py` accepts `--lpipe-samples N` (default: `LPIPE_SAMPLES_DEFAULT = 1`; use `LPIPE_SAMPLES_REPLICATION = 3` for replication runs). When N > 1, the L-pipe subprocess is called N times per incident with the same seed+prompt, producing N `ranked_candidates` lists. The per-sample HR@3 scores are recorded in `lpipe_hr_at_3_samples`. Borda fusion uses the majority-vote `ranked_candidates` (most common top-1 across samples) when N > 1.

L-pipe variance across samples in `lpipe_hr_at_3_samples` is surfaced in `m4_exploratory_analysis.json` and annotated as a determinism diagnostic, not a primary metric.

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

def test_ties_stable_under_input_reordering(candidates):
    """Ties must resolve identically regardless of the order candidates are passed in."""

def test_no_consensus_fallback():
    """GatedComponentInactiveError propagates to caller; fuse() itself does not reference D-pipe."""
```

### 5.4 Integration test: `--dry-run` (new)

File: `tests/integration/test_run_ablation_dry_run.py`

`run_ablation.py` must support a `--dry-run` flag that:
- Launches all 8 variant subprocesses as mocked shell commands (no real Ollama/pipeline calls)
- Writes synthetic per-variant DuckDB files with 20×3=60 placeholder rows each
- Exercises the full manifest-write → integrity-check → smoke-check → atomic-merge path
- Asserts: manifest contains 8 entries, central DB has correct row count, backup is cleaned up

```python
def test_dry_run_full_pipeline(tmp_path, monkeypatch):
    """Full run_ablation.py --dry-run exercises manifest + integrity + smoke + merge."""
    # Mock subprocess.run to write synthetic DB files instead of running pipelines
    ...
    result = subprocess.run(
        ["poetry", "run", "python", "scripts/run_ablation.py",
         "--dry-run", "--corpus", str(tmp_path / "corpus"),
         "--output-db", str(tmp_path / "central.duckdb")],
        check=True,
    )
    manifest = json.loads((tmp_path / "m4_variant_manifest.json").read_text())
    assert len(manifest) == 8  # NUM_VARIANTS
    central_db = duckdb.connect(str(tmp_path / "central.duckdb"))
    row_count = central_db.execute("SELECT COUNT(*) FROM pipeline_verdicts").fetchone()[0]
    assert row_count == EXPECTED_PIPELINE_ROW_COUNT
```

### 5.5 G4-5 smoke: noConsensus path

`fuse_verdicts.py --smoke` must exercise both:
1. `HELIOS-Full` (RECONCILE=True): `fusion_algorithm="uniform_borda_v1"`, Borda fuse path
2. `HELIOS-noConsensus` (RECONCILE=False): `fusion_algorithm="none"`, D-pipe passthrough path

The `--smoke` flag selects 2 incidents from the first HELIOS-Full variant and 2 incidents from the first HELIOS-noConsensus variant, covering both code paths in a single CI run.

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

On lineage failure: append a deviation log entry, write to `ExclusionLedger`, and mark the affected cell with `excluded = True` in the `consensus_verdicts` table (or write a tombstone row with `fusion_algorithm = "excluded"`). Cells that are missing or excluded must never reach `analyse_results.py`.

### 6.1a Exclusion ledger filter gate (fix #3)

`analyse_results.py` must filter the ConsensusVerdict table before computing any statistics:

```python
def load_analysis_rows(store: ResultStore) -> list[ConsensusVerdict]:
    """Load only complete, non-excluded consensus cells."""
    all_rows = store.fetch_all_consensus_rows()
    complete = [
        r for r in all_rows
        if r.pipeline_row_count == 3 and r.fusion_algorithm != "excluded"
    ]
    excluded_count = len(all_rows) - len(complete)
    if excluded_count > 0:
        logger.warning(
            "Excluded %d cells from analysis (pipeline_row_count < 3 or excluded flag). "
            "See exclusion_ledger.jsonl for details.",
            excluded_count,
        )
    return complete
```

If the filtered set is smaller than `NUM_INCIDENTS * NUM_VARIANTS`, the analysis output must record the actual N used per hypothesis pair, not the expected N. Statistical conclusions must reference the actual N.

### 6.2 Idempotency key

Fusion is keyed on `(source_run_sha, FUSION_CORE_VERSION)`. If a `ConsensusVerdict` row already exists for this key and `--overwrite` was not passed, the run is a no-op and exits cleanly.

### 6.3 `--smoke` flag (G4-5)

```bash
python scripts/fuse_verdicts.py --smoke
```

Runs lineage assertion and fuses only the first 2 incidents (4 cells). Exits 0 if all ConsensusVerdict rows are well-formed. Used in CI as a fast gate.

### 6.4 Ground truth SHA verification

At the start of `fuse_verdicts.py`, verify the SHA:

```python
actual_sha = sha256(Path("data/ground_truth.json").read_bytes()).hexdigest()
expected_sha = load_corpus_manifest()["ground_truth_sha"]
if actual_sha != expected_sha:
    raise RuntimeError(
        f"ground_truth.json SHA mismatch.\n"
        f"  expected: {expected_sha}\n"
        f"  actual:   {actual_sha}\n"
        "If you corrected a label, run: python scripts/compile_ground_truth.py --update-manifest"
    )
```

The error message must reference the `--update-manifest` path (Section 2.2a) so the operator knows the correct remediation action rather than assuming the file is corrupted.

---

## Section 7 — Statistical Inference

### 7.1 `scripts/analyse_results.py`

Consumes `ConsensusVerdict` rows and `helios/research/analysis_plan.py` to run Wilcoxon tests.

```python
import scipy.stats
import numpy as np

def run_wilcoxon(x: list[float], y: list[float], hypothesis_id: str) -> dict:
    differences = [a - b for a, b in zip(x, y)]
    nonzero_diffs = [d for d in differences if d != 0]

    # Zero-variance guard — two conditions (fix #5):
    # (a) all differences are zero (std = 0, test undefined)
    # (b) all non-zero differences are identical (std of non-zero subset = 0);
    #     e.g., every pair differs by exactly +0.1 — scipy produces undefined ranks
    if len(nonzero_diffs) == 0 or np.std(nonzero_diffs) == 0:
        return {
            "hypothesis_id": hypothesis_id,
            "result": "INVARIANT",
            "n_nonzero": len(nonzero_diffs),
            "note": (
                "All non-zero differences are identical or all differences are zero; "
                "Wilcoxon signed-rank test not applicable"
            ),
        }

    try:
        stat, p_value = scipy.stats.wilcoxon(
            x, y,
            alternative="two-sided",
            method="exact",
        )
    except ValueError as exc:
        # Catch any remaining edge cases scipy raises (e.g., N=1 after zero removal)
        return {
            "hypothesis_id": hypothesis_id,
            "result": "WILCOXON_ERROR",
            "error": str(exc),
            "n_nonzero": len(nonzero_diffs),
        }

    # Matched-pairs rank-biserial r: r = 1 - (2W) / (n_nonzero(n_nonzero+1)/2)
    # Uses n_nonzero (not total N) because scipy excludes zero-difference pairs.
    # r ∈ [-1, 1]: positive = treatment wins more ranks; negative = control wins.
    n_nz = len(nonzero_diffs)
    max_w = n_nz * (n_nz + 1) / 2
    rank_biserial_r = float(1 - (2 * stat) / max_w)

    return {
        "hypothesis_id": hypothesis_id,
        "statistic": stat,
        "p_value": p_value,
        "rank_biserial_r": rank_biserial_r,
        "n": len(x),
        "n_nonzero": n_nz,
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

### 7.4 Per-pipeline HR@3 (on-demand join)

`analyse_results.py` does NOT read `hr_at_3_dpipe/gpipe/lpipe` from `ConsensusVerdict` (those fields were removed). Instead, it joins:

```python
# Pseudocode for per-pipeline HR@3 computation
pipeline_rows = store.fetch_all_pipeline_rows()  # PipelineVerdict table
consensus_rows = store.fetch_all_consensus_rows()  # ConsensusVerdict table

for cv in consensus_rows:
    matching = [
        r for r in pipeline_rows
        if r.incident_id == cv.incident_id
        and r.variant_config_hash == cv.variant_config_hash
    ]
    per_pipeline_hr = {r.pipeline: r.hr_at_3 for r in matching}
```

This keeps the ConsensusVerdict schema normalised and prevents HR@3 values from drifting out of sync with the underlying PipelineVerdict rows.

### 7.5 Output

Results written to `results/m4_exploratory_analysis.json`. This file is the evidence artefact for G4-6. Each per-hypothesis entry includes:
- `statistic`, `p_value`, `rank_biserial_r`, `n`
- `per_pipeline_hr_at_3`: `{d_pipe: float, g_pipe: float, l_pipe: float}` (from join)
- `lpipe_variance_diagnostic`: `{sample_count: int, hr_at_3_variance: float}` (from `lpipe_hr_at_3_samples`)

The `rank_biserial_r` field allows the Chapter 4 dissertation text to argue practical significance when N=20 is insufficient to achieve statistical significance at the pre-registered α.

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

## Environment Fingerprint
- Git commit: <M4 exit SHA — fill at exit>
- Python: 3.11.x (exact patch version)
- poetry.lock SHA: <fill at M4 exit via sha256sum poetry.lock>
- Docker Compose hash: <sha256 of docker/otel-demo/compose.yaml>
- OTEL Demo image tag: <fill at exit — must be pinned in compose.yaml>
- ABLATION_SEED: SEED-S1-01 (see seed_register.md)
- FUSION_CORE_VERSION: borda-v1
- FUSION_ALGORITHM_SHA: <fill at M4 exit — output of _compute_ast_hash() at run time>
- LPIPE_SAMPLES: 3 (replication mode)

## Full Reproduction Commands
1. git checkout <M4 exit SHA>
2. poetry install
3. docker compose -f docker/otel-demo/compose.yaml up -d
4. python scripts/compile_ground_truth.py
5. python scripts/run_ablation.py --rollback-on-failure --lpipe-samples 3
6. python scripts/fuse_verdicts.py
7. python scripts/analyse_results.py
8. python scripts/replicate.py  # byte-equality check against reference hashes

## Replicate Without Docker (2-incident subset)
python scripts/replicate.py --n-incidents 2  # uses pre-captured snapshots from data/captures/
```

---

## Section 10 — Exit Gates

| Gate | ID | Criterion | Evidence artefact |
|---|---|---|---|
| UniformBordaConsensus tests pass | G4-1 | pytest + hypothesis property tests all green | CI run |
| ConsensusVerdict schema frozen | G4-2 | schema-draft-v0.3 committed; deviation entry logged | deviation_log.jsonl |
| 160 consensus cells computed | G4-3 | 20 incidents × 8 variants; 0 nulls in ConsensusVerdict table | results/fused_verdicts.db |
| Lineage assertion passes | G4-4 | exactly 480 pipeline rows; all cells complete (3 rows each) | fuse_verdicts.py output |
| Smoke test passes | G4-5 | `fuse_verdicts.py --smoke` exits 0; exercises both HELIOS-Full (Borda path) and HELIOS-noConsensus (passthrough path) | CI job |
| Wilcoxon results generated | G4-6 | all 8 A-hypotheses in `results/m4_exploratory_analysis.json`; each entry includes `rank_biserial_r` | results/ |
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
| `helios/config/__init__.py` | Create | Module init |
| `helios/config/m4_ablation.py` | Create | All M4 constants: counts, floors, paths, sample params |
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
| `tests/integration/test_run_ablation_dry_run.py` | Create | Full dry-run integration test: manifest + integrity + smoke + atomic merge |

---

## Section 12 — Constraints and Invariants

- **RunOrchestrator is frozen.** `_build_verdict()` must not be modified. HR@3 set to zero in `PipelineVerdict` is correct — HR@3 is computed by `analyse_results.py` via join.
- **`helios/config/m4_ablation.py` is the single source of truth** for all counts, floors, and paths. No script may redeclare `EXPECTED_PIPELINE_ROW_COUNT`, `HR_AT_3_FLOOR`, or output filenames as literals.
- **PipelineVerdict is frozen.** Schema-draft-v0.2 unchanged. `ConsensusVerdict` is schema-draft-v0.3, a separate type.
- **FUSION_CORE_VERSION must change** if the Borda algorithm logic changes. Changing comments or whitespace does not require a version bump. Any bump requires a deviation log entry.
- **ground_truth.json SHA is locked** in `corpus_manifest.json` at M3 OSF freeze. `fuse_verdicts.py` must verify it before fusion.
- **Two-environment firewall:** OTEL corpus = exploratory only. Results from M4 are never used as confirmatory evidence. `evaluation_phase = "exploratory"` is hardcoded for all M4 runs.
- **Holm-Bonferroni α:** Pre-registered α = 0.00625 per hypothesis applies at confirmatory phase. M4 inference uses standard exploratory α; confirmatory correction applied in Phase 2 only.
- **Coverage gate:** pytest `--cov-fail-under=90` must not regress. New modules need tests before the gate is run.
- **research-compliance hook:** Avoid word-bounded float literals for zero, one, one-half, and one-hundred in any committed file. Use named constants in Python code; use prose in Markdown.
- **Seeds must come from seed_register.md.** Never declare a seed value as a bare integer literal in any script. Import `LLAMA_SEED` / `ABLATION_SEED` from the config module.
