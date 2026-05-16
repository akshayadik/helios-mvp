# HELIOS Project — Architecture, Design & Execution Reference

**Version:** Milestone 2 (2026-05-16)
**Stage:** D-pipe + UEG-C skeleton complete. G/L pipelines remain stubs.
**Python:** `>=3.11,<3.12` (strict upper bound — reproducibility commitment)
**Repo:** `helios-mvp` · Primary branch: `main`

---

## Table of Contents

1. [What HELIOS Is](#1-what-helios-is)
2. [Research Design](#2-research-design)
3. [System Architecture](#3-system-architecture)
4. [Variant Control Layer (VCL)](#4-variant-control-layer-vcl)
5. [Data Schemas](#5-data-schemas)
6. [Orchestration & C1 Enforcement](#6-orchestration--c1-enforcement)
7. [Audit Infrastructure](#7-audit-infrastructure)
8. [CI/CD Workflows](#8-cicd-workflows)
9. [Execution Commands](#9-execution-commands)
10. [Missing Details & Gaps](#10-missing-details--gaps)
11. [Milestone Tracking & Production Delta](#11-milestone-tracking--production-delta)

---

## 1. What HELIOS Is

HELIOS (**H**ybrid **E**xplainable **L**earning for **I**ncident **O**bservability and **S**upervision) is a doctoral research artefact built around Design Science Research (DSR) methodology. It is a hybrid multi-pipeline Root Cause Analysis (RCA) framework for microservice incidents in production cloud environments.

**Core thesis:** Existing RCA tools treat observability modalities (traces, logs, metrics) in isolation, lengthening MTTR. HELIOS fuses three peer pipelines over all three modalities simultaneously.

**Three peer pipelines:**
| Pipeline | Modality | Algorithm | Flag |
|---|---|---|---|
| D-pipe | Metrics | Statistical correlation + propagation (Pearson/Spearman, PPR) | `dpipe` |
| G-pipe | Traces + topology | Graph causal traversal (UEG-C + PPR) | `gpipe` / `l2b_graph` |
| L-pipe | Logs + all | LLM explanation via Protocol A (Llama-3.1-70B) | `lpipe` / `l2c_llm` |

Results are fused by a **Uniform Borda consensus layer** into a single ranked candidate list.

**Primary metric:** HR@3 (Hit-Rate at rank 3) — was the root-cause service in the top-3 candidates?
**Secondary metrics:** CpR (Causal Precision-Recall), hallucination rate (L-pipe), CoE narrative quality, MTTR delta.

---

## 2. Research Design

### 2.1 Evaluation Environments

| Environment | Purpose | `evaluation_phase` value |
|---|---|---|
| OTEL Demo (local K8s) | Exploratory calibration only | `exploratory` |
| AIOpsLab (cloud benchmark) | All confirmatory inference | `confirmatory` |

**Two-environment firewall:** Any row with `evaluation_phase = "exploratory"` is permanently excluded from all confirmatory analyses. This is enforced at the data-collection layer and cannot be relaxed without a deviation log entry.

### 2.2 Confirmatory Hypotheses (Family A — Ablation)

Statistical test: paired Wilcoxon signed-rank (one-sided), Holm–Bonferroni correction.
**n = 174** incident pairs. **α at rank 1 = 0.00625**.

| Rank | ID | Comparison | Primary metric |
|---|---|---|---|
| 1 | A-H3 | HELIOS-Full vs HELIOS-D | HR@3 |
| 2 | A-H7 | HELIOS-Full vs HELIOS-noLLM | HR@3 |
| 3 | A-H1 | HELIOS-Full vs fixed threshold 0.60 | HR@3 |
| 4 | A-H2 | HELIOS-Full vs HELIOS-noGraph | CpR |
| 5 | A-H6 | HELIOS-G vs HELIOS-D (gate-conditional) | HR@3 |
| 6 | A-H5 | HELIOS-Full vs HELIOS-noRouter | HR@3 |
| 7 | A-H4 | HELIOS-Full vs HELIOS-noConsensus | HR@3 — underpowered-disclosed |
| 8 | A-H8 | HELIOS-Full vs HELIOS-noStructural | HR@3 — underpowered-disclosed |

**Effect size commitment:** Cohen's h ≥ 0.276. Target HR@3 = 0.73 vs CHASE baseline HR@3 = 0.60.

### 2.3 Ablation Matrix

**16,000 runs** — 8 variants × 5 benchmarks × 40 faults × 10 seeds (AIOpsLab confirmatory).

### 2.4 C1 — Runtime-Enforced Ablation Discipline

C1 is the headline methodological contribution. It is a system of seven sub-artefacts that guarantee every measurement run is tagged with a content-hashed variant identity and that ablation code paths are provably disjoint:

| Sub-artefact | Module | Stage frozen |
|---|---|---|
| VCL (variant control layer) | `helios/vcl/` | Stage 0 |
| Deviation log (HMAC-chained) | `bin/log_deviation.py` | Stage 0 |
| SnapshotRegistry (L2 guard) | `helios/vcl/snapshot_registry.py` | Stage 0 |
| MetricIntegrityGate | `helios/integrity_gate.py` | Milestone 1 |
| ExclusionLedger | `bin/log_exclusion.py` | Milestone 1 |
| ReconciliationLedger | `helios/orchestrator/ledger.py` | Milestone 1 |
| DisjointnessAuditor | `helios/vcl/disjointness.py` | Milestone 1 |

---

## 3. System Architecture

### 3.1 Observability Layers

```
L0  CaptureReader          helios/telemetry/reader.py
      │  TelemetryWindow (5-min multi-modal window — metrics, traces, logs, events, profiles)
      │  Hash verified on read (SHA-256 round-trip guard)
      │
      ▼  [D-pipe — Milestone 2]
      ·  Statistical anomaly detection → UEGCSnapshot construction
      │
      ▼
L2  SnapshotRegistry       helios/vcl/snapshot_registry.py
      │  Content-addressable JSONL: snapshot_hash → variant_config_hash
      │  Pre-condition gate: every pipeline run must pass a registered snapshot_hash
      │
      ▼
L2  Pipeline Dispatch       helios/pipelines/{d,g,l}_pipe/pipeline.py
      │  Three peer pipelines dispatch concurrently per incident
      │  Each gated by @gated_by(VCLFlag.X)
      │
      ▼
L2  MetricIntegrityGate    helios/integrity_gate.py
      │  Validates: required fields + variant_config_hash match + cross-pipeline snapshot_hash agreement
      │  FAIL → ExclusionLedger.append() + ReconciliationLedger.record(outcome="excluded")
      │
      ▼
L2  ResultStore             helios/store/result_store.py  (DuckDB)
      │  3 × result_row inserts per PASS incident (one per pipeline)
      │
      ▼
    ReconciliationLedger   helios/orchestrator/ledger.py
         HMAC-chained JSONL: one row per incident, outcome ∈ {passed, excluded, skipped}
```

### 3.2 Module Map

```
helios/
├── vcl/                    Variant Control Layer (C1 core) — FULLY IMPLEMENTED
│   ├── registry.py         VCLFlag enum (14 flags)
│   ├── config.py           VCLManifest (Pydantic, frozen, SHA-256 hash)
│   ├── variants.py         8 confirmatory VCLManifest instances
│   ├── decorators.py       @gated_by, set_current_manifest, get_current_manifest
│   ├── hmac_chain.py       HMACChainedLog base class
│   ├── snapshot_registry.py SnapshotRegistry
│   ├── disjointness.py     DisjointnessAuditor (static + coverage.py audit)
│   └── utils.py            canonical_json (sorted keys, 6-decimal floats)
│
├── graph/                  Milestone 2 — FULLY IMPLEMENTED
│   ├── ueg_c_builder.py    UEGCBuilder (structural + call edges)
│   └── ppr_pruner.py       PPR Pruner (noise reduction gate)
│
├── schemas/                Frozen at schema-draft-v0.2
│   ├── telemetry.py        TelemetryWindow (L0), EvaluationPhase
│   ├── ueg_c.py            UEGCNode, UEGCEdge, UEGCSnapshot, EdgeClass (computed)
│   └── verdict.py          PipelineVerdict (result row)
│
├── orchestrator/           Milestone 1 — FULLY IMPLEMENTED
│   ├── corpus.py           CorpusLoader (directory or JSON manifest)
│   ├── ledger.py           ReconciliationLedger
│   └── runner.py           RunOrchestrator (full C1 dispatch loop)
│
├── pipelines/              D-pipe (M2) complete; G/L remain stubs
│   ├── d_pipe/             Stages A–D: Metrics, Anomaly, Propagation, Verdict
│   ├── g_pipe/stub.py      @gated_by(VCLFlag.GPIPE) — returns sentinel dict
│   └── l_pipe/stub.py      @gated_by(VCLFlag.LPIPE) — returns sentinel dict
│
├── integrity_gate.py       MetricIntegrityGate + AppendOnlyLedger protocol
├── store/result_store.py   DuckDB result store (result_row table)
└── telemetry/reader.py     CaptureReader + CaptureVerification

bin/
├── helios_run.py           CLI entry point — `helios run` corpus orchestration
├── log_deviation.py        HMAC deviation log CLI (append + verify)
├── log_exclusion.py        ExclusionLedger stub (Stage 1+)
├── run_capture.py          OTEL Demo telemetry capture
└── verify_captures.py      Hash round-trip verification
```

---

## 4. Variant Control Layer (VCL)

### 4.1 Flag Registry (`helios/vcl/registry.py`)

14 flags — 13 boolean + 1 string operational flag:

```python
class VCLFlag(StrEnum):
    # 12 proposal flags (Table 12 / §3.6.7)
    L2C_LLM = "l2c_llm"          # L-pipe LLM
    P4_COGNITIVE = "p4_cognitive"  # P4 cognitive layer
    MAHC = "mahc"                  # MAHC consensus
    CBR = "cbr"                    # Case-based reasoning
    L2B_GRAPH = "l2b_graph"       # Graph causal inference
    ACP = "acp"                    # Adaptive context protocol
    RECONCILE = "reconcile"        # Reconciliation module
    UEG_C_STRUCTURAL = "ueg_c_structural"  # Structural edges
    DPIPE = "dpipe"                # D-pipe enable
    DPIPE_PROPAGATION = "dpipe_propagation"
    GPIPE = "gpipe"                # G-pipe enable
    LPIPE = "lpipe"                # L-pipe enable
    ROUTER = "router"              # Cross-pipeline routing
    INGEST_MODE = "ingest_mode"   # "recorded" | "live" — NOT a boolean gate
```

**`VCLFlag.bool_flags()`** — returns the 13 boolean flags excluding `INGEST_MODE`. Always use this when iterating flags for audit or gating. Never use `@gated_by(VCLFlag.INGEST_MODE)` — it raises `TypeError` at decoration time.

### 4.2 Manifest (`helios/vcl/config.py`)

`VCLManifest` is Pydantic v2, `frozen=True`, `extra="forbid"`.

```python
manifest = VCLManifest.from_flags(l2c_llm=True, dpipe=True, ..., ingest_mode="recorded")
config_hash = manifest.compute_variant_config_hash()
# → SHA-256(canonical_json(manifest.model_dump()))
# canonical_json: sorted keys, floats rounded to 6 decimal places, no whitespace
```

**Hash stability rule:** adding a field to `VCLManifest` changes all variant hashes. Any such change requires a deviation log entry with `analytic_consequence`.

### 4.3 Gating Decorator (`helios/vcl/decorators.py`)

```python
@gated_by(VCLFlag.DPIPE)
def run_dpipe(window: TelemetryWindow, ...) -> dict[str, Any]: ...
```

- Raises `TypeError` at decoration time if the flag is not boolean.
- Raises `GatedComponentInactiveError` at call time if the flag is `False` in the active manifest.
- Sets `__gated_by__` attribute on the function for static disjointness audit.
- Uses `ContextVar` — call `set_current_manifest(manifest)` before invoking any gated function.

### 4.4 Confirmatory Variants (`helios/vcl/variants.py`)

| Variant | Key flags off | Hypothesis |
|---|---|---|
| HELIOS-Full | — | A-H1, A-H3, B-H1..B-H8 |
| HELIOS-noLLM | l2c_llm, lpipe | A-H7 |
| HELIOS-noGraph | l2b_graph, gpipe | A-H2 |
| HELIOS-D | l2c_llm, mahc, cbr, l2b_graph, acp, reconcile, gpipe, lpipe, router | A-H3 |
| HELIOS-G | l2c_llm, mahc, cbr, acp, reconcile, dpipe_propagation, lpipe, router | A-H6 |
| HELIOS-noConsensus | mahc | A-H4 |
| HELIOS-noRouter | router | A-H5 |
| HELIOS-noStructural | ueg_c_structural | A-H8 |

```python
from helios.vcl.variants import get_variant
manifest = get_variant("HELIOS-Full")
```

### 4.5 Disjointness Audit (`helios/vcl/disjointness.py`)

`DisjointnessAuditor` performs two checks:
1. **Static** — inspects `__gated_by__` attributes on all pipeline functions; verifies every boolean flag has coverage
2. **Dynamic** — `coverage.py` context runs (`HELIOS-Full` vs `HELIOS-noGraph`) flag any line covered by both active and inactive paths

Run manually: `poetry run python -m helios.vcl.disjointness`

---

## 5. Data Schemas

All schemas frozen at tag `schema-draft-v0.2`. All use Pydantic v2 `frozen=True`, `extra="forbid"`.

### 5.1 TelemetryWindow (`helios/schemas/telemetry.py`)

L0 5-minute multi-modal capture window.

| Field | Type | Notes |
|---|---|---|
| `incident_id` | `str` | Fault event identity |
| `variant_config_hash` | `str` (64-char hex) | VCLManifest identity |
| `window_start_iso` / `window_end_iso` | ISO 8601 UTC | 5-min window bounds |
| `evaluation_phase` | `EvaluationPhase` | `exploratory` or `confirmatory` |
| `p1_metrics_path` … `p5_profiles_path` | `str \| None` | Parquet stream paths |
| `schema_version` | `str` | Default `schema-draft-v0.1` |

`compute_window_hash()` — SHA-256 of canonical JSON.

### 5.2 UEGCSnapshot (`helios/schemas/ueg_c.py`)

L1/L2 canonical graph snapshot.

| Field | Type | Notes |
|---|---|---|
| `incident_id` | `str` | Links to fault event |
| `variant_config_hash` | `str` (64-char hex) | VCLManifest identity |
| `nodes` | `list[UEGCNode]` | 5 node types: service, operation, pod, database, external |
| `edges` | `list[UEGCEdge]` | 4 edge types (see below) |
| `captured_at_iso` | ISO 8601 UTC | Capture timestamp |
| `schema_version` | `str` | Default `schema-draft-v0.1` |

**Edge taxonomy:**

| `EdgeType` | `EdgeClass` (computed) | Gated by |
|---|---|---|
| `structural` | STRUCTURAL | `ueg_c_structural` |
| `call` | BEHAVIOURAL | `l2b_graph` |
| `metric` | CAUSAL | `dpipe` |
| `log` | ECONOMIC | `l2b_graph` |

`edge_class` is a Pydantic `@computed_field` — auto-derived from `edge_type`, never stored, always consistent.

`compute_snapshot_hash()` — SHA-256 of canonical JSON. Hash is stored in `result_row`, not in the snapshot itself (avoids circular dependency).

### 5.3 PipelineVerdict (`helios/schemas/verdict.py`)

Per-pipeline result row written to DuckDB.

| Field | Type | Constraint | Notes |
|---|---|---|---|
| `run_id` | `str` | PRIMARY KEY | Unique per verdict — each incident gets 3 distinct UUIDs |
| `incident_id` | `str` | FK | Links verdict to incident |
| `variant_config_hash` | `str` (64-char hex) | C1 invariant | Must match active manifest |
| `snapshot_hash` | `str` (64-char hex) | C1 invariant | Cross-pipeline must agree |
| `pipeline` | `str` | `dpipe\|gpipe\|lpipe` | Source pipeline |
| `evaluation_phase` | `EvaluationPhase` | Enum | Exploratory or confirmatory |
| `ranked_candidates` | `list[str]` | Ordered | Top-k service names (HR@3 source) |
| `hr_at_3` | `float` | `[0–1]` | Hit-Rate@3 |
| `cpr` | `float` | `[0–1]` | Causal Precision-Recall |
| `latency_ms` | `float` | `>= 0` | Wall-clock latency |
| `token_count` | `int` | `>= 0` | LLM tokens (L-pipe) or 0 |
| `narrative` | `str` | Non-empty | Chain of Explanation (CoE) |
| `schema_version` | `str` | Default `schema-draft-v0.1` | |

`compute_verdict_hash()` — SHA-256 of canonical JSON.

---

## 6. Orchestration & C1 Enforcement

### 6.1 RunOrchestrator (`helios/orchestrator/runner.py`)

Full C1 dispatch loop for a corpus. Per incident:

```
CorpusLoader.incident_ids()
  → CaptureReader.read(incident_id)       — L0 hash guard; outcome=skipped on mismatch
  → build_ueg_c() + prune_graph()         — Milestone 2 graph construction
  → SnapshotRegistry.register(hash)       — L2 identity guard
  → run_dpipe + run_gpipe + run_lpipe     — 3 pipeline dispatch (each @gated_by)
  → MetricIntegrityGate.check_consistency(rows)
      FAIL → ExclusionLedger.append() + ReconciliationLedger.record("excluded")
      PASS → ResultStore.insert() ×3 + ReconciliationLedger.record("passed")
```

**Critical:** `_build_verdict()` generates a fresh `uuid.uuid4()` per verdict — not the per-incident `run_id`. This is required because `result_row.run_id` is the PRIMARY KEY and three verdicts per incident would collide. Incident-level correlation is via `incident_id`.

### 6.2 CorpusLoader (`helios/orchestrator/corpus.py`)

Accepts two corpus formats:

```python
# Directory mode — any subdirectory containing manifest.json
loader = CorpusLoader(Path("data/captures/"))

# JSON manifest mode
# data/corpus.json: {"incidents": ["inc-001", "inc-002", ...]}
loader = CorpusLoader(Path("data/corpus.json"))
```

### 6.3 ReconciliationLedger (`helios/orchestrator/ledger.py`)

HMAC-chained JSONL. One row per incident per run.

```python
ledger = ReconciliationLedger(key=hmac_key, log_path=Path("reconciliation_ledger.jsonl"))
ledger.record(run_id=..., incident_id=..., variant_config_hash=..., outcome="passed")
# outcomes: attempted | passed | excluded | skipped
```

Verify chain integrity: `ok, msg = ledger.verify()`

### 6.4 MetricIntegrityGate (`helios/integrity_gate.py`)

Validates result rows before they enter the result store:

1. All required fields present (`variant_config_hash`, `snapshot_hash`, `run_id`)
2. `variant_config_hash` matches the active manifest
3. Across all pipeline rows: `snapshot_hash` values are identical

On any failure: auto-writes to `AppendOnlyLedger` (ExclusionLedger) and returns `GateResult(status="FAIL")`.

### 6.5 ResultStore (`helios/store/result_store.py`)

DuckDB-backed result store. Tables: `result_row`, `schema_tag`.

```python
store = ResultStore(Path("data/results.duckdb"))
store.insert(verdict)                           # inserts one PipelineVerdict row
rate = store.inclusion_rate(variant_config_hash) # fraction of pipelines present
```

---

## 7. Audit Infrastructure

### 7.1 HMACChainedLog (`helios/vcl/hmac_chain.py`)

Base class for all three append-only audit logs. Each entry is HMAC-SHA256 signed over its full content plus the previous entry's signature, forming a tamper-evident chain.

```python
log = HMACChainedLog(key=hmac_key, log_path=Path("log.jsonl"))
log.append({"field": "value", ...})   # signs and appends
ok, msg = log.verify()                 # walks chain from GENESIS
```

**Post-sign fields** (not included in signature payload): `signature`, `deviation_id`. Any new derived field must be added to `_UNSIGNED_KEYS`.

### 7.2 Deviation Log (`bin/log_deviation.py`)

Every protocol change with analytic consequence must be logged here before merging.

```bash
set -a; source .env; set +a

# Append entry
poetry run python bin/log_deviation.py \
  --stage "Stage N" \
  --clause "§..." \
  --change "..." \
  --reason "..." \
  --analytic-consequence "..."

# Verify chain
poetry run python bin/log_deviation.py verify
```

Requires `DEVIATION_HMAC_SECRET` (≥ 32 chars) in `.env` — gitignored, back up in password manager.

### 7.3 ExclusionLedger (`bin/log_exclusion.py`)

Records C1 gate failures. Seven required fields: `variant_config_hash`, `snapshot_hash`, `run_id`, `incident_id`, `gate_check`, `reason`, `analytic_consequence`.

> **Status:** Stage 1+ stub. The CLI defines the schema but real population happens via `MetricIntegrityGate._fail()` through the `AppendOnlyLedger` protocol.

---

## 8. CI/CD Workflows

### `.github/workflows/ci.yml` — 5 sequential jobs

```
lint → typecheck → test → tracking
                        → disjointness (parallel with tracking)
```

| Job | What it runs | Gate |
|---|---|---|
| **lint** | `ruff check` + `ruff format --check` + `black --check` | Blocks typecheck |
| **typecheck** | `mypy helios/` + `mypy scripts/` (strict) | Blocks test |
| **test** | `pytest` (full suite) + `pytest tests/test_schema_roundtrip.py -v` | Blocks tracking + disjointness |
| **tracking** | `python scripts/validate_tracking.py` | Catches `--no-verify` bypasses |
| **disjointness** | Static `python -m helios.vcl.disjointness` | §3.9.1 Threat 2 |

- Runner: `ubuntu-22.04` (pinned, not floating)
- Poetry: `pip install "poetry==1.8.4"` (not pipx)
- Coverage gate: `--cov-fail-under=90` enforced via `pyproject.toml addopts`
- Coverage XML uploaded as artifact (14-day retention)
- `concurrency.cancel-in-progress: true` — cancels stale runs on rapid pushes

### `.github/workflows/disjointness_audit.yml` — PR-only

Two-phase audit:

```yaml
- poetry run python -m helios.vcl.disjointness          # static __gated_by__ scan
- coverage run --context=HELIOS-Full -m pytest tests/
- coverage run --append --context=HELIOS-noGraph -m pytest tests/
- coverage report --show-contexts --include="helios/pipelines/*"
```

### `.github/workflows/ledger_verification.yml`

Verifies HMAC chain of `deviation_log.jsonl` on every push. Requires `DEVIATION_HMAC_SECRET` in GitHub Secrets.

---

## 9. Execution Commands

### First-time setup

```bash
# Generate HMAC secret
python3 -c "import secrets; print(f'DEVIATION_HMAC_SECRET={secrets.token_urlsafe(32)}')" > .env
chmod 600 .env

# Install (Python 3.11 required)
poetry env use python3.11
poetry install
poetry run pre-commit install
```

### Pre-push gate (run before every PR — exact CI sequence)

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ && \
  poetry run ruff format --check helios/ scripts/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

### Testing

```bash
# Full suite
poetry run pytest

# Verbose
poetry run pytest -v

# With coverage report
poetry run pytest --cov=helios --cov-report=term-missing

# Specific test files
poetry run pytest tests/test_deviation_log.py -v           # HMAC canary (12 tests)
poetry run pytest tests/test_validate_tracking.py -v      # tracking validator
poetry run pytest tests/test_schema_roundtrip.py -v       # schema freeze check
poetry run pytest tests/test_orchestrator_runner.py -v    # RunOrchestrator (4 tests)
poetry run pytest tests/test_disjointness.py -v           # disjointness auditor
```

### Lint and type-check

```bash
poetry run ruff check helios/ scripts/ tests/         # lint
poetry run ruff check --fix helios/ scripts/ tests/   # auto-fix
poetry run ruff format helios/ scripts/ tests/        # format
poetry run mypy                                        # type-check (strict)
```

### Tracking document validation

```bash
make validate-tracking   # schema check (R1–R8); exit 0 = clean
make test-tracking       # pytest suite for the validator itself
```

### Corpus run (full C1 pipeline)

```bash
set -a; source .env; set +a

# Directory corpus (auto-discovers subdirs with manifest.json)
poetry run python bin/helios_run.py \
  --variant HELIOS-Full \
  --corpus data/captures/

# JSON manifest corpus
poetry run python bin/helios_run.py \
  --variant HELIOS-noLLM \
  --corpus data/corpus.json \
  --db data/results.duckdb \
  --registry data/snapshot_registry.jsonl \
  --reconciliation reconciliation_ledger.jsonl
```

### Deviation log

```bash
set -a; source .env; set +a

# Append a signed entry
poetry run python bin/log_deviation.py \
  --stage "Stage N" \
  --clause "§X.Y.Z" \
  --change "Brief description of change" \
  --reason "Why the change was necessary" \
  --analytic-consequence "Impact on research claims"

# Verify full chain
poetry run python bin/log_deviation.py verify
```

### Disjointness audit (manual)

```bash
poetry run python -m helios.vcl.disjointness

# Full dynamic audit
poetry run coverage run --context=HELIOS-Full -m pytest tests/ -q
poetry run coverage run --append --context=HELIOS-noGraph -m pytest tests/ -q
poetry run coverage report --show-contexts --include="helios/pipelines/*"
```

### Telemetry capture (OTEL Demo — requires environment running)

```bash
set -a; source .env; set +a

poetry run python bin/run_capture.py --incident-id s0-adhc-001
poetry run python bin/verify_captures.py   # verify hash round-trip (run 3×)
```

### Stage gate tagging

```bash
git tag stage-N-exit
git push origin stage-N-exit
```

---

## 10. Missing Details & Gaps

The following are known gaps as of Milestone 2. Each is intentional (staged implementation) unless marked ⚠️.

### Stubs not yet implemented

| Component | Module | Target stage | Notes |
|---|---|---|---|
| G-pipe real implementation | `helios/pipelines/g_pipe/` | Stage 4 | Graph causal traversal on UEG-C |
| L-pipe real implementation | `helios/pipelines/l_pipe/` | Stage 5 | Llama-3.1-70B, Protocol A, vLLM serving |
| Consensus layer (Uniform Borda) | not yet created | Stage 6 | Fuses D/G/L ranked lists |
| Auto-remediation (L4) | not yet created | Stage 4+ | Out of MVP scope |
| P4 cognitive layer | no module yet | Stage 5 | `p4_cognitive` flag exists; implementation pending |
| MAHC, CBR, ACP | no modules yet | Stage 3+ | Flags exist in VCL; no implementations |

### Data & corpus gaps

| Item | Status | Notes |
|---|---|---|
| AIOpsLab confirmatory corpus (174 incidents) | **Not started** | Stage 2+; requires AIOpsLab access and fault injection |

---

## 11. Milestone Tracking & Production Delta

### 11.1 Immediate Pending Actions (Milestone 2 Exit)

| # | Action | Command / Location | Blocker for |
|---|---|---|---|
| 1 | Push `milestone-2-exit` tag to origin | `git push origin milestone-2-exit` | Milestone 2 sign-off |
| 2 | Push `schema-draft-v0.2` tag to origin | `git push origin schema-draft-v0.2` | Schema freeze proof |
| 3 | Finalize deviation log entries for M2 | `bin/log_deviation.py verify` | Audit compliance |

### 11.2 Missing Details with respect to C1

*   **PPR Determinism:** The current `ppr_pruner.py` relies on `networkx.pagerank`. While mathematically deterministic, subtle floating-point drift across different CPU architectures (x86 vs ARM) could violate C1 snapshot-hash stability in distributed environments. A pre-M4 gate requires a fixed-point or rounded implementation.
*   **Ablation Disjointness (G-pipe/L-pipe):** While D-pipe is now fully implemented and gated, G-pipe and L-pipe remain null stubs. The `DisjointnessAuditor` currently only proves that the *entry points* are disjoint. Full path-disjointness proof is deferred to Stage 7.
*   **Integrity Gate (P4/P5):** The `MetricIntegrityGate` currently ignores P4 (events) and P5 (profiles) because they are `None` in the OTEL Demo. The logic must be extended in Milestone 6 to fail if these are missing during AIOpsLab confirmatory runs.

### 11.3 Component Roles Reconciled (Research vs. Production)

| Component | Research harness (current) | Production deployment |
|---|---|---|
| **VCL / VCLManifest** | Frozen per-run config for ablation attribution. | Runtime feature-flag fingerprint for deployment audit. |
| **UEG-C Builder** | Batch extractor using temporal span-containment heuristic. | Live graph builder using deterministic `parent_span_id` linkage. |
| **PPR Pruner** | Static noise-reduction gate for small demo clusters. | Dynamic graph sharding / pruning for 1000+ service meshes. |
| **D-pipe Stages** | Sequential batch stages (`A` -> `B` -> `C` -> `D`). | Parallel stream-processing pipelines (Kafka/Flink). |
| **Calibration Set** | 15 incidents used for offline threshold tuning. | "Golden Signal" baseline used for online drift detection. |

### 11.4 What Gets Removed vs. Added in Production

**Removed (research-only constructs):**
- **Span-Containment Heuristic:** Replaced by strict OTEL parent-child causality.
- **`calibrate_dpipe.py`:** Replaced by an automated online "Baseline Watcher" service.
- **Ablation-specific variants:** `HELIOS-noLLM`, `HELIOS-noGraph`, etc., are archived; only `HELIOS-Full` remains active.
- **Static Disjointness Audit:** Replaced by standard unit/integration testing for the single production path.

**Added (production requirements):**
- **Live Ingestion Bridge:** Prometheus remote-write / Jaeger stream-tailer.
- **Graph Database:** Transition from in-memory NetworkX to Neo4j or Memgraph for scalability.
- **Consensus Microservice:** The Uniform Borda layer implemented as a stand-alone, low-latency scoring service.
- **Alertmanager Integration:** Webhook receiver to trigger the `RunOrchestrator` on active alerts.
- **L4 Auto-remediation:** Integration with Kubernetes operators to apply "healing" actions (e.g., vertical scaling) based on D-pipe/G-pipe verdicts.

---

*Generated from Milestone 2 codebase state at commit `d78d29e`. Update this file after each stage gate.*
