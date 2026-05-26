# VCL — Variant Control Layer: Implementation Details
**Contribution C1 — Runtime-Enforced DSR Evaluation Rigour**
*HELIOS · Stage 0 Frozen · All components implemented and tested*

---

## What is the VCL?

The Variant Control Layer (VCL) is the primary methodological contribution (C1) of the dissertation.
It makes pre-registration discipline **architecturally enforced** — not a reporting convention.
Every experimental run carries a cryptographic identity. Every deviation is signed and chained.
No variant can silently differ from its pre-registered configuration.

In DSR terms: VCL transforms the evaluation plane from a *claiming* layer into a *proving* layer.

---

## Components and Responsibilities

### 1. Flag Registry (`helios/vcl/registry.py`)

**Responsibility:** Single source of truth for all 14 feature flags.

| Flag | Type | Controls |
|---|---|---|
| `l2c_llm` | bool | LLM reasoning in L-pipe |
| `p4_cognitive` | bool | Cognitive telemetry (P4) |
| `mahc` | bool | Multi-Agent Hybrid Consensus |
| `cbr` | bool | Case-Based Routing |
| `l2b_graph` | bool | Graph edges (call + log) |
| `acp` | bool | Action-Class Predictor |
| `reconcile` | bool | Reconciliation ledger |
| `ueg_c_structural` | bool | Topology (structural) edges in UEG-C |
| `dpipe` | bool | D-pipe statistical pipeline |
| `dpipe_propagation` | bool | D-pipe anomaly propagation stage |
| `gpipe` | bool | G-pipe graph pipeline |
| `lpipe` | bool | L-pipe LLM pipeline |
| `router` | bool | Cost-minimising ORAR bandit router |
| `ingest_mode` | string | `"recorded"` or `"live"` (operational, not gatable) |

`VCLFlag.bool_flags()` returns the 13 boolean flags safe for `@gated_by`.
`VCLFlag.INGEST_MODE` is always excluded from gating — it is an operational string flag.

---

### 2. Configuration Manifest (`helios/vcl/config.py`)

**Responsibility:** Immutable variant identity — every run's cryptographic fingerprint.

```python
class VCLManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    # 13 boolean flags + ingest_mode + model_version + prompt_template_id
    ...
    def compute_variant_config_hash(self) -> str:
        # SHA-256(canonical_json(self.model_dump()))
```

**Key design decisions:**
- `frozen=True` — assignment raises `ValidationError`; manifests are immutable after construction
- `extra="forbid"` — canonical JSON is exhaustive; adding a field without updating the model breaks hash stability
- `canonical_json()` pre-normalises floats to 6 decimal places before `json.dumps` (required because `json.dumps` never calls `default()` for native Python `float` — a silent bug if handled differently)
- `@field_validator("ingest_mode")` fires on every construction path (direct, `from_flags`, deserialization)
- `model_version` and `prompt_template_id` are included in the hash for C1 stability

**Input:** 13 boolean flags + `ingest_mode` + `model_version` + `prompt_template_id`
**Output:** `VCLManifest` instance with deterministic `variant_config_hash` (64-char hex)

---

### 3. Gating Decorator (`helios/vcl/decorators.py`)

**Responsibility:** Enforce that gated components only execute when their controlling flag is active.

```python
@gated_by(VCLFlag.LPIPE)
def run_lpipe(snapshot: UEGCSnapshot, ...) -> PipelineVerdict:
    ...
```

**Mechanics:**
- **Decoration time:** raises `TypeError` if the flag is not a boolean flag (e.g., `INGEST_MODE` cannot be gated)
- **Call time:** reads active manifest from `ContextVar`; raises `GatedComponentInactiveError` if flag is `False`
- **Audit hook:** sets `function.__gated_by__` attribute for static disjointness audit
- **Thread/async safety:** uses `ContextVar` — no shared state across concurrent pipeline runs
- `set_current_manifest(manifest)` must be called before invoking any gated component

**Input:** `VCLFlag` (enum value) at decoration time; active `VCLManifest` via `ContextVar` at call time
**Output:** either the wrapped function's result, or `GatedComponentInactiveError`

---

### 4. Variant Registry (`helios/vcl/variants.py`)

**Responsibility:** Pre-registered, version-controlled ablation variant definitions.

- **8 confirmatory variants** (frozen at Stage 0; hashes locked at OSF freeze Milestone 3)
- **7 exploratory variants** (OTEL Demo calibration; excluded from confirmatory analysis)
- `get_variant(name)` → `VCLManifest`: resolves name to manifest; confirmatory first, then exploratory
- Any change to a variant definition is visible in `git diff` and requires a deviation log entry if it has analytic consequence
- All variants share `ingest_mode="recorded"` (primary evaluation protocol)
- `router=True` is the manifest default; only `HELIOS-noRouter` overrides it

**Input:** variant name (string)
**Output:** `VCLManifest` with all 14 flags set per the pre-registered specification

---

### 5. Snapshot Registry (`helios/vcl/snapshot_registry.py`)

**Responsibility:** L2 analysis identity gate — every UEGCSnapshot must be registered before any pipeline runs on it.

| Method | Behaviour |
|---|---|
| `register(snapshot_hash, variant_config_hash)` | Append-only JSONL; raises `DuplicateSnapshotError` if already registered |
| `contains(snapshot_hash)` | Pre-condition check before pipeline dispatch |
| `all_hashes()` | Audit listing — insertion-ordered |
| `verify()` | Raises `DuplicateSnapshotError` on any duplicate in the file |

**Current state:** 20 entries in `data/snapshot_registry.jsonl` (20 incidents recorded and registered)

**Input:** `snapshot_hash` + `variant_config_hash` (both 64-char lowercase hex, enforced by `_validate_hex64`)
**Output:** append-only JSONL; `contains()` gates pipeline entry

---

### 6. HMAC-Chained Deviation Log (`bin/log_deviation.py`, `helios/vcl/hmac_chain.py`)

**Responsibility:** Cryptographically signed, append-only record of every protocol departure with analytic consequence.

**Mechanics:**
- Each entry: `{stage, clause, change, reason, analytic_consequence, deviation_id, timestamp, prev_signature, signature}`
- `signature = HMAC-SHA256(key=DEVIATION_HMAC_SECRET, msg=canonical_json(entry_without_sig))`
- `prev_signature` chains to the previous entry — tampering any entry invalidates all subsequent signatures
- `deviation_id` is derived from `signature` (post-sign field) and excluded from the signed payload via `_UNSIGNED_KEYS`
- Chain verification: `poetry run python bin/log_deviation.py verify`
- Secret in `.env` (gitignored); also required in GitHub Secrets for CI `ledger_verification.yml`

**Current state:** 18 entries, chain verified. Most recent entries: sequential dispatch change (13), G-pipe threshold change (14), L-pipe model deviation (15–16).

**Input:** `--stage`, `--clause`, `--change`, `--reason`, `--analytic-consequence` (CLI)
**Output:** signed JSONL entry appended to `deviation_log.jsonl`

---

### 7. Disjointness Auditor (`helios/vcl/disjointness.py`)

**Responsibility:** Verify that each feature flag toggles exactly one disjoint code path — no hidden coupling.

- **Static audit (CI):** inspects `__gated_by__` attributes registered by `@gated_by` decorator
- **Dynamic audit:** `coverage.py` ON/OFF diffs — flag-ON and flag-OFF runs produce non-overlapping branch coverage
- **Current status:** 5 flags covered (gpipe, dpipe, l2c_llm, l2b_graph, mahc), 8 uncovered, 0 violations
- One hidden coupling was identified and resolved at design freeze: `p4_cognitive` flag was scoped to L-pipe only (removing cognitive nodes from G-pipe's input was silent before the fix)
- CI workflow: `disjointness_audit.yml` — exits 0 on `ImportError` until full audit module is complete (Phase 2)

**Input:** source files in `helios/pipelines/` + `helios/vcl/` decorator registry
**Output:** coverage-diff report; fails CI if any flag toggles a path that another flag also owns

---

### 8. Supporting Modules

| Module | Purpose |
|---|---|
| `helios/vcl/utils.py` | `canonical_json()` — sorted keys, 6-decimal float normalisation, no whitespace |
| `helios/vcl/__init__.py` | Public API exports: `VCLFlag`, `VCLManifest`, `gated_by`, `get_current_manifest`, `set_current_manifest`, `get_variant` |

---

## VCL Interactions with Other Layers

```
┌──────────────────────────────────────────────────────────────────┐
│                      VCL (C1 Enforcement)                         │
│                                                                    │
│  ┌─────────────┐    ┌───────────────┐    ┌──────────────────┐   │
│  │ FlagRegistry │    │  VCLManifest  │    │  DeviationLog    │   │
│  │ (registry.py)│    │  (config.py)  │    │  (hmac_chain.py) │   │
│  └──────┬──────┘    └───────┬───────┘    └────────┬─────────┘   │
│         │                   │                      │              │
│         └──────────┬────────┘                      │              │
│                    │                                │              │
│  ┌─────────────────▼──┐  ┌──────────────┐         │              │
│  │  @gated_by         │  │  Snapshot    │         │              │
│  │  (decorators.py)   │  │  Registry    │         │              │
│  └─────────────────┬──┘  └──────┬───────┘         │              │
└────────────────────┼────────────┼──────────────────┼──────────────┘
                     │            │                  │
          ┌──────────▼──┐  ┌──────▼────┐   ┌───────▼─────────┐
          │ D-pipe /    │  │ UEGCSnapshot│  │ Orchestrator    │
          │ G-pipe /    │  │ (L1 output)│  │ (runner.py)     │
          │ L-pipe      │  └────────────┘  └─────────────────┘
          │ (L2 peers)  │
          └──────┬──────┘
                 │ PipelineVerdict (variant_config_hash + snapshot_hash stamped)
                 ▼
          ┌──────────────┐    ┌─────────────────┐    ┌───────────────────┐
          │ Metric       │    │ Exclusion        │    │ Reconciliation    │
          │ Integrity    │    │ Ledger           │    │ Ledger            │
          │ Gate         │    │ (FAIL path)      │    │ (reward audit)    │
          └──────────────┘    └─────────────────┘    └───────────────────┘
```

---

## VCL Design Principles Summary

| Principle | Mechanism | Where enforced |
|---|---|---|
| Single source of truth | All flags in one `VCLManifest` | `registry.py` + `config.py` |
| Deterministic identity | `SHA-256(canonical_json(manifest))` | `config.py` + `utils.py` |
| Runtime enforcement | `@gated_by` + `ContextVar` + `GatedComponentInactiveError` | `decorators.py` |
| Auditability | `__gated_by__` registration + static CI + dynamic coverage-diff | `decorators.py` + `disjointness.py` |
| Immutability | `frozen=True, extra="forbid"` (Pydantic v2) | `config.py` |
| Reproducibility | Canonical JSON (sorted keys, 6-decimal floats, no whitespace) | `utils.py` |
| Protocol tamper-evidence | HMAC-SHA256 chained signatures | `hmac_chain.py` |
| Completeness enforcement | `metric_integrity_gate` rejects incomplete cells | `helios/integrity_gate.py` |
