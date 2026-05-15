# Reproducibility Manifest

**Purpose:** Cumulative SHA-256 of corpus, container digests, replication scripts, model versions, and price book. Source for OSF deposit and Appendix B. Proves byte-level reproducibility of every confirmatory run.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** Weekly + Stage 5 freeze (when this document is deposited to OSF)
**Owner:** AA
**Lock target:** Stage 5 OSF deposit

---

## Section 1 — Environment (frozen at Milestone 1)

All values below are pinned and must not change without a deviation log entry.

| Component | Version / Pin | Pin mechanism | Notes |
|---|---|---|---|
| Python | `>=3.11,<3.12` | `pyproject.toml python` constraint | Upper bound is a reproducibility commitment, not preference |
| Poetry | `1.8.4` | `pip install "poetry==1.8.4"` in CI | Locked in `.github/workflows/ci.yml` |
| ruff | `>=0.6.9,<0.7` | `pyproject.toml + ci.yml` | `preview=true` required; range pinned in both files |
| mypy | per `poetry.lock` | `pyproject.toml` extras | Strict mode; version from lock file |
| OTEL Demo | v2.2.0 | `external/otel-demo-pinned @ b74a7bc` | Pinned as git submodule at fixed commit |
| HELIOS codebase | Milestone 1 | tag `milestone-1-exit` | SHA `f11c529` |

---

## Section 2 — Schema Freeze

| Schema artefact | Git tag | Commit SHA | Frozen at |
|---|---|---|---|
| TelemetryWindow + UEGCSnapshot + PipelineVerdict | `schema-draft-v0.1` | `d58a878` | Milestone 1 |

**Round-trip CI test:** `tests/test_schema_roundtrip.py` — serialise → deserialise → SHA-256 compare on every push. Any field addition breaks the test and requires a schema version bump + deviation log entry.

---

## Section 3 — Exploratory Corpus (Milestone 1)

| Item | Value |
|---|---|
| Environment | OTEL Demo v2.2.0 |
| Incident count | 20 |
| Fault classes | 4 (Resource, Dependency, Network, Code) |
| Evaluation phase | exploratory (permanently excluded from confirmatory analysis) |
| Registry file | `data/snapshot_registry.jsonl` (20 entries) |
| Verification | `bin/verify_captures.py` — all 20 OK, 3x repeat |

---

## Section 4 — Stage 5 Items (ALL PENDING)

These items must NOT be committed before Stage 5 to prevent corpus selection bias (OSF protocol §3.3). Recording them early is a protocol deviation.

| Item | Status | Target stage |
|---|---|---|
| AIOpsLab corpus manifest SHA-256 (174 incidents) | `[PENDING: Stage 5]` | Stage 5 OSF freeze |
| BCa bootstrap seed (10,000 resamples, Family E) | `[PENDING: Stage 5]` | Stage 5 OSF freeze |
| L-pipe prompt template SHA-256 (Protocol A) | `[PENDING: Stage 5]` | Stage 5 OSF freeze |
| vLLM container image digest | `[PENDING: Stage 5]` | Stage 5 OSF freeze |
| Ollama container image digest (fallback) | `[PENDING: Stage 5]` | Stage 5 OSF freeze |
| AIOpsLab incident selection seed | `[PENDING: Stage 5]` | Stage 5 OSF freeze |
| Price book (token costs at analysis time) | `[PENDING: Stage 5]` | Stage 5 OSF freeze |

---

*Last updated: 2026-05-15 — Sections 1–3 complete; Section 4 pending Stage 5*
