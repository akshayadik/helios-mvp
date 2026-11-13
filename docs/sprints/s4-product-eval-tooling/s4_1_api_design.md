# S4.1 API: design (draft)

**Row:** S2-M9-ENG01 · **Effort:** 1½ days · **Depends on:** S2.7 (CoE ledger), S4.9 (stored runs) · **Feeds:** S4.3 (compose), S4.2 (approval console, the RQ4 instrument) · **Status:** draft 2026-11-14, for owner approval (A-a to A-j)

## 1. What is fixed already

- **Task** (`helios_task_breakdown.md` S4.1): incidents, verdicts, CoE, HITL decisions, health; API keys; OpenAPI spec; contract tests.
- **e2e plan:** API (incidents, verdicts, CoE, decisions) and docker-compose deployment are Tier 1 in S4; Helm is Tier 3.
- **Done when (S4 plan):** OpenAPI spec and contract tests. S4.2 then needs RQ4 timing capture: E-H7 measures time to decision, Full vs noExpl.
- **Integrity rules that apply to anything that reads results:**
  - ground truth, case names and injection times are never exposed (contract §1, D11 §3);
  - confirmatory runs stay locked until `build-freeze` (`pool_lock`);
  - every recorded decision goes into an append-only, signed ledger, like every other HELIOS record.

## 2. What exists today

| Piece | State |
|---|---|
| Results | DuckDB store per campaign: `fusion_row` (ranked list, scores, confidence, state, publication times), `narrative_row` (rendered text, slots, grounding), `trigger_row`, `evidence_row`, `eval_score` / `eval_run` (scored, label-derived) |
| CoE | One HMAC-chained entry per run, Ed25519-signed anchor (`helios/orchestrator/coe.py`), verifiable with the public key alone |
| Verdict states | CONFIRMED (automatic), PROVISIONAL and NON_CONVERGED (go to a human, `requests_human`) |
| HTTP | Only `bin/label_server.py` (stdlib `http.server`, loopback, keys in the URL fragment, signed annotations ledger). No web framework in the dependencies |
| HITL decisions | Not stored anywhere yet |

## 3. Decisions for the owner

### A-a. Framework

- **Recommended: FastAPI with uvicorn.**
  - The OpenAPI spec is generated from the same pydantic models the code already uses (pydantic is pinned `>=2.9,<2.10`; FastAPI 0.115 supports it).
  - Validation, typed responses and the test client come with it.
  - It is the production-grade choice the product direction asks for.
  - Cost: three new dependencies (fastapi, uvicorn, httpx for tests), pinned in `pyproject.toml` and `poetry.lock`.
- (b) The stdlib server, like the label server: no new dependencies, but the OpenAPI spec would be written and kept in sync by hand.

### A-b. Scope of v1: read verdicts, record decisions; runs stay in the CLI

- **Recommended:**
  - the API reads stored runs and records HITL decisions;
  - runs are still started by `bin/helios_run.py` and the campaign CLI.
- Why runs stay out of the API:
  - a run takes seconds to minutes (the L-pipe), so it would need a job queue;
  - a confirmatory run must never be startable from a web request.
- `POST /v1/runs` (submit a recorded capture as a background job) moves to Stage B with live ingestion.
- (b) Include run submission now, with a single-worker job queue.

### A-b2. Endpoints (v1)

| Method and path | What it returns or does | Role |
|---|---|---|
| `GET /health` | Status, API and schema versions, store schema tags, ledger verification (CoE, decisions), whether `build-freeze` exists. No result data | none (loopback only) |
| `GET /v1/incidents` | Incidents with runs: incident ID, number of runs, latest run's variant, state, confidence and top 3. Paged | reader |
| `GET /v1/incidents/{incident_id}` | Every run of the incident, summarised | reader |
| `GET /v1/verdicts/{run_id}` | The fused verdict: ranked services with scores, confidence, state, publication times (first, terminal), trigger time and suspects, routing (escalated or not), narrative (rendered text, claims with evidence IDs) | reader |
| `GET /v1/verdicts/{run_id}/coe` | The run's CoE entry (steps and evidence) and its verification result | reader |
| `POST /v1/verdicts/{run_id}/views` | Opens a review: a signed view token carrying the server time it was issued (A-e) | reviewer |
| `POST /v1/verdicts/{run_id}/decisions` | Records accept, escalate or reject with the view token and an optional note; returns the ledger entry | reviewer |
| `GET /v1/verdicts/{run_id}/decisions` | Decisions recorded for the run | reader |

- **Never returned:** `eval_score`, `eval_run` or anything label-derived (HR@k, TTCD, CpR). Those carry ground truth; they stay with the analysis.
- **Variant visibility:** a run's variant name is shown. For a run whose variant has `coe_narrative` off (HELIOS-noExpl), `narrative` is null. That is the E-H7 condition, and it comes from the stored run, not from a client toggle.

### A-c. Data source and concurrency

- **Recommended:**
  - the API opens one campaign store, read-only (`duckdb.connect(read_only=True)`), named in its config;
  - the CoE ledgers come from that campaign's `coe/` folder.
- **Limitation:** DuckDB allows one writer process per file, and a read-only open fails while a campaign is writing. The API therefore serves a store no campaign is writing to, and says so in `/health`. A live product store with concurrent writes is Stage B.
- **Pool lock:** a confirmatory run is refused (HTTP 423) until `build-freeze`, through the same `pool_lock` check the reader uses.

### A-d. Authentication and roles

- **Recommended:**
  - API keys sent in the `X-API-Key` header and compared in constant time;
  - keys stored only as SHA-256 hashes in a key file (`api_keys.json`, outside git, mode 0600), each with an ID and roles;
  - a `keygen` CLI prints a new key once.
- **Roles:** `reader` (GET), `reviewer` (reader plus views and decisions), `admin` (reserved).
- **Network:** the API binds to loopback by default; anything wider is the compose file's choice (S4.3).
- **Secrets:** keys are never logged, and the server refuses to start with any `DEVIATION_*` variable in its environment (as the label server does).
- (b) No auth on loopback in S4: simpler, but the task asks for API keys and S4.2's study needs per-participant keys.

### A-e. Decision timing (RQ4 instrument)

- **Recommended: server-side timing.**
  - `POST /views` returns a token: run ID, key ID, issue time, HMAC-signed with the decisions key.
  - `POST /decisions` must carry an unexpired token for the same run and key.
  - The server records `shown_at`, `decided_at` and `decision_ms` from its own clock, and stores the client's own measure beside it (`client_ms`, optional).
  - The server's figure is the one E-H7 uses, so a participant's browser can't alter it.
- **Token rules:**
  - a token can be used once;
  - a token expires after 30 minutes (Ch3's incident window), after which the decision is refused and the view has to be reopened;
  - reopening is recorded, so abandoned views are visible.
- (b) Client-side timing only: simpler, but not tamper-evident.

### A-f. Decisions ledger

- **Recommended:** decisions go to a new append-only `DecisionLedger`, an HMAC-chained log with a signed anchor like the other ledgers, one per campaign directory.
  - **Fields:** run ID, incident ID, variant hash, key ID, decision, note, `shown_at`, `decided_at`, `decision_ms`, `client_ms`, view token digest.
  - **Key:** its own secret (`HELIOS_DECISIONS_HMAC_SECRET`), never the deviation-log key.
  - **Verification:** `bin/verify_ledgers.py --campaign` gains a check for it.
- A decision is never edited. A changed mind is a second decision, and the latest counts.
- (b) A DuckDB table: simpler to query, but not tamper-evident.

### A-g. OpenAPI spec and versioning

- **Recommended:**
  - the spec is generated from the app and committed as `docs/api/openapi.json`;
  - a test fails if the app's spec and the committed file differ, so the spec can't drift silently;
  - paths are versioned (`/v1`), and the spec carries `info.version` = `api-v1`.
- **Errors** use RFC 9457 problem details (`application/problem+json`), so the console and any client get one error format.

### A-h. Contract tests

- **Recommended:**
  - tests against a fixture store built with the real `ResultStore` and `CoELedger` (two runs, one with each verdict state, one noExpl run, one confirmatory run);
  - every endpoint, role and error (401, 403, 404, 409 token reuse, 410 token expired, 423 pool locked) is checked against the committed spec's response schemas;
  - a leakage test asserts that no response contains a ground-truth field, a case name or an injection time.
- (b) Also property-based fuzzing with schemathesis: broader, but another dependency and slower CI. Could be added in S5.

### A-i. Feature flag and module layout

- **Code:**
  - `helios/api/` (app factory, routes, models, auth, decisions ledger);
  - `bin/helios_api.py` (`serve`, `keygen`, `export-spec`).
- **Flag:** the API is product shell, not a pipeline component, so it gets no new VCL flag (a new flag would change every variant hash). It carries `HELIOS_ENABLE_API` (flag-guard), and it only reads what the flags already decided.

### A-j. Dry run

- `bin/helios_api.py serve` against the OTel v3 build campaign store (`camp_v3c`, 1,121 runs). Then, through the API:
  1. list incidents;
  2. open a PROVISIONAL verdict with its narrative and its CoE entry, the CoE verifying;
  3. open a review, record a decision, and read back the signed entry with server-side timing;
  4. check that a noExpl run returns no narrative;
  5. check that no response contains a label.

## 4. Deviation entry

- **None expected.** The API changes no pre-registered rule, metric or variant.
- E-H7's time to decision becomes the server-measured `decision_ms` (A-e). That is the measurement the pre-registration's "time to decision" needs, not a change to it. If you'd rather record it, it can go in the OSF addendum (S2-BL-05).
