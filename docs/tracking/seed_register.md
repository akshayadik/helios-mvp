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

*Superseded 2026-10-24 by the binding seed register (S0.8, deviation entry 34). The May plan of 10 seeds × 8 variants × 5 benchmarks no longer applies: the evidence design is one run per (case, system) on 240 recorded cases (D11, entry 25).*

The confirmatory seeds are not listed row by row here: each is pure arithmetic on frozen inputs, so the rule and the layout are what is registered. Source of truth: `helios/research/seeds.py`; frozen copy: `research/osf/seeds.json` (in OSF deposit 1, layout_sha256 `ce0cab374e9a7d66a7c996266afbca3175665f8d148bf7b034ff7b7a000f871f`).

| Block | Seeds | Rule |
|---|---|---|
| run | 10,000,000–10,007,199 | first seed + case position in the sealed pool order × 24 + system slot (15 variants, 5 baselines, 4 spare) |
| training | 10,007,200–10,007,327 | first seed + component slot × 8 + replicate (0 binding, 1–5 robustness) |
| bca | 10,007,328–10,007,391 | one per hypothesis, in analysis-plan order |
| opaque_id | 10,007,392–10,007,407 | one per corpus |
| prewarm | 10,007,408–10,008,607 | one per pre-warm incident |
| reserved | 10,008,608–10,009,999 | new blocks only by deviation entry |

| Seed_ID | Seed_value | Stage | Variant | Benchmark | Registered | Algorithm_context | SHA | Notes |
|---------|------------|-------|---------|-----------|------------|-------------------|-----|-------|
| SEED-SA0-01 | 10000000 | Stage A / S0 | ALL | ALL | 2026-10-24 | First seed of the binding register; every confirmatory, training, BCa, opaque-ID and pre-warm seed derives from it by the block layout above | a91534f | Deviation entry 34; `SEED_REGISTRY` SEED-003 in `helios/research/seeds.py` |

---

## Cross-References

- `reproducibility_manifest.md` — full environment + software pin list
- `vcl_manifest_tracking.md` — variant_config_hash for each variant (paired with seeds)
- `deviation_log.jsonl` — any seed change with analytic consequence is logged there
