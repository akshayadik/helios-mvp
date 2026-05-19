# Seed Register

**Purpose:** Register every integer seed used in any experiment run, mapping seed value to run context, so that any result can be reproduced exactly by re-running with the same seed and the same VCL manifest.

**Update frequency:** Append-only; one row per seed-variant-benchmark combination at run time. Never edit or delete rows.

**Schema freeze:** Columns are frozen at Stage 1 exit. New columns require a deviation log entry.

---

## Column Schema

| Column | Type | Required | Immutable | Description |
|--------|------|----------|-----------|-------------|
| Seed_ID | string | ✅ | ✅ | Format: `SEED-{stage}-{nn}` (e.g. `SEED-S0-01`) |
| Seed_value | integer | ✅ | ✅ | The integer seed value passed to NumPy default RNG |
| Stage | string | ✅ | ✅ | Stage in which this seed was registered (e.g. `Stage 0`) |
| Variant | string | ✅ | ✅ | VCL variant name (e.g. `HELIOS-Full`) |
| Benchmark | string | ✅ | ✅ | Benchmark ID or `ALL` if applied globally |
| Registered | date | ✅ | ✅ | Date of first use (ISO 8601) |
| Algorithm_context | string | ✅ | ✅ | What the seed controls (e.g. `NumPy default RNG — fault injection order`) |
| SHA | string | ✅ | ✅ | Commit SHA of the code that first used this seed |
| Notes | string | ❌ | ❌ | Free text; populated if seed was changed (requires deviation log entry) |

---

## Design Rules

1. **Fixed seeds only.** Seeds are never drawn at runtime — they are committed in advance and referenced by Seed_ID.
2. **Pre-registration.** Seeds for confirmatory runs must be registered in this document and committed *before* those runs execute (Stage 5 requirement).
3. **Deviation log entry required** for any seed change that affects a metric result. Non-analytic changes (documentation typo fix) do not require a deviation log entry.
4. **Seeds apply to:** fault injection order, benchmark sub-sampling, and any stochastic component in D-pipe / G-pipe / L-pipe.
5. **L-pipe (LLM) temperature:** LLM API calls use `temperature=0` for determinism; no seed is required for the LLM component. This is noted in `reproducibility_manifest.md`.

---

## Registered Seeds

### Stage 0 — Exploratory Telemetry Captures

| Seed_ID | Seed_value | Stage | Variant | Benchmark | Registered | Algorithm_context | SHA | Notes |
|---------|------------|-------|---------|-----------|------------|-------------------|-----|-------|
| SEED-S0-01 | 42 | Stage 0 | HELIOS-Full | AIOpsLab | 2026-05-14 | NumPy default RNG — incident ordering for exploratory capture sequence | 489f2c7 | Exploratory only; excluded from confirmatory analysis |

---

### Stage 1 / M3 — L-pipe Protocol A

| Seed_ID | Seed_value | Stage | Variant | Benchmark | Registered | Algorithm_context | SHA | Notes |
|---------|------------|-------|---------|-----------|------------|-------------------|-----|-------|
| SEED-S1-01 | 42 | Stage 1 / M3 | ALL | ALL | 2026-05-19 | Ollama Protocol A inference seed — controls greedy decoding reproducibility in L-pipe via `LLAMA_SEED` constant in `lpipe_config.py` | 3340abc | Exploratory phase; used alongside temperature=0 for deterministic LLM output. Applies to all L-pipe-enabled variants. Not applicable to L-pipe-disabled variants (e.g., HELIOS-noLLM). |

---

## Confirmatory Seed Block (Stage 5+)

[PENDING: Stage 5 — 10 seeds × 8 variants × 5 benchmarks to be pre-registered before confirmatory runs begin. Seeds will be drawn by the OSF pre-registration script and committed here atomically with the Stage 5 deviation log entry.]

---

## Cross-References

- `reproducibility_manifest.md` — full environment + software pin list
- `vcl_manifest_tracking.md` — variant_config_hash for each variant (paired with seeds)
- `deviation_log.jsonl` — any seed change with analytic consequence is logged there
