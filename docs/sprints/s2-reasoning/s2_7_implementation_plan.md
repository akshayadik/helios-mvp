# S2.7 Chain-of-Evidence ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One signed, append-only CoE entry per stored incident run — every decision in order with its evidence under one ID namespace (D/G/L + T/R/F/G) — HMAC-chained per entry, anchor Ed25519-signed, the single citation source for the S2.8 narrator.

**Flag:** the ledger is audit infrastructure and always on; `VCLFlag.COE_NARRATIVE` gates only the S2.8 narrator.

**Architecture:** `helios/vcl/hmac_chain.py` gains an opt-in anchor-only Ed25519 mode (`ANCHOR_ED25519 = True`; deviation log unchanged). `helios/orchestrator/coe.py` holds `CoELedger` and `build_coe_entry`. D-pipe returns `coe_evidence` (stored as an `evidence_row`, pipeline `dpipe`). The runner builds and appends the entry in the PASS branch; confirmatory runs refuse a missing Ed25519 key. `bin/verify_ledgers.py --coe <dir>` verifies CoE files.

**Tech Stack:** Python 3.11, cryptography (Ed25519, existing), duckdb, pydantic v2; pytest.

**Spec:** `docs/sprints/s2-reasoning/s2_7_coe_ledger_design.md` (approved 2026-10-31). Row **S2-M7-ENG07**.

## Global Constraints

- HMAC on every entry; after each entry the anchor (entries, head, `log_sha256`) is Ed25519-signed when the private key is present; no per-entry Ed25519 signature for CoE (C-a). The deviation log's per-entry Ed25519 (entry 35) is unchanged.
- An anchor without the key is marked unsigned; `verify_public` reports it unsigned, never verified. Confirmatory runs refuse a missing key in `_trigger_for`.
- One namespace (C-b): `D:<service>:<signal>`, `G:<service>:<feature>`, `L:<worker>:<line>`, decisions `T`, `R`, `F`, `G` (gate). Items `{id, service, text, value}`; IDs unique within an entry.
- Soft cap: at most 30 items per pipeline, but every L-pipe worker claim and every line it cites are always kept; D-pipe items for its top 5 services.
- Entries only for runs whose verdicts are stored (PASS); none for excluded runs.
- `refs`: SHA-256 of the canonical JSON of each stored row the step summarises.
- No ground-truth field, fault label (OTel flag names, RCAEval case names) or injection time in an entry; real service names are expected.
- D-pipe's ranked list, mu, sigma and decision hash unchanged; the new output is named `coe_evidence` (the internal `evidence` dict feeds sigma).
- CoE file next to the results DB: `<db_path stem>.coe.jsonl`; same Ed25519 key pair as the deviation log.
- Never edit an `.anchor.json`; never `cd`; never `git commit -a`; check exit codes; full local gate; deviation entry signed before merge; local `--no-ff` merge on the owner's go-ahead; no push.

## Review Focus

1. **A run where every pipeline abstained or failed** (no fused list): the CoE entry is still written with the decisions and empty item lists; nothing crashes. *(Task 4 test)*
2. **An L-pipe claim that cites a line beyond the 30-item cap:** the line is kept. *(Task 4 test)*
3. **A CoE ledger appended across two runner instances** (same file): the chain continues and the anchor re-signs. *(Task 2 test)*
4. **noLLM / D / G variants** (L-pipe skipped): entry valid, no `L:` items, `P:lpipe` status skipped. *(Task 5 test)*
5. **An unsigned anchor later appended with a key present:** the next anchor is signed and `verify_public` passes. *(Task 2 test)*

---

### Task 1: Open the row

- [ ] Branch `s2/coe` from local `main`; commit the design note and this plan; row S2-M7-ENG07 IN_PROGRESS (Started 2026-10-31, Deps S2-M7-ENG05); validator exit 0 and row parsed; commit.

### Task 2: Anchor-only Ed25519 mode and `CoELedger`

**Files:** Modify `helios/vcl/hmac_chain.py`; Create `helios/orchestrator/coe.py` (ledger class); Test `tests/test_coe_ledger.py`.

**Interfaces — Produces:**
- `HMACChainedLog.ANCHOR_ED25519: bool = False` — when True: no per-entry Ed25519; `_write_anchor` adds `log_sha256` and `anchor_ed25519_signature` when a private key is loaded, else `"anchor_unsigned": true`.
- `verify_public(..., from_entry: int | None, ...)` — `None` skips per-entry Ed25519 checks (bytes are covered by the signed anchor digest); an anchor with `anchor_unsigned` returns `(False, "Anchor is unsigned ...")`.
- `CoELedger(HMACChainedLog)`: `LOG_KIND = "coe"`, `ANCHOR_ED25519 = True`, `REQUIRED_FIELDS = ("run_id", "incident_id", "variant_config_hash", "snapshot_hash", "evaluation_phase", "steps")`.

- [ ] **Step 1: tests:** `test_coe_verifies_hmac_and_public` (3 entries with a test key pair); `test_tamper_edit_remove_reorder_truncate_fail` (each fails `verify()` and `verify_public`); `test_unsigned_anchor_is_reported_unsigned`; `test_unsigned_then_signed_append_verifies` (Review Focus 5); `test_two_instances_continue_the_chain` (Review Focus 3); `test_deviation_log_still_verifies_public` (the real `deviation_log.jsonl`, public key, `from_entry=35`).
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.

### Task 3: D-pipe `coe_evidence`

**Files:** Modify `helios/pipelines/d_pipe/pipeline.py`; Test `tests/pipelines/d_pipe/test_coe_evidence.py`.

**Interfaces — Produces:** `run_dpipe` output key `coe_evidence = {"services": [{"service", "shift", "score", "final"}, ...]}` for the top 5 ranked services: `shift` = the internal `evidence[service]` (robust units, None if absent), `score` = pre-propagation score, `final` = final score; empty list when abstained.

- [ ] **Step 1: tests:** `test_coe_evidence_top5_fields`; `test_ranking_mu_sigma_and_decision_hash_unchanged` (two build-like fixtures: the PipelineVerdict decision hash equals the value computed from the output without `coe_evidence`); `test_abstained_has_empty_evidence`.
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.

### Task 4: CoE entry builder

**Files:** Modify `helios/orchestrator/coe.py`; Test `tests/test_coe_entry.py`.

**Interfaces — Produces:**
- `ITEM_CAP = 30`; `row_ref(row: Mapping[str, Any]) -> str` (SHA-256 of canonical JSON).
- `build_coe_entry(*, run_id, incident_id, variant_config_hash, snapshot_hash, evaluation_phase, parameter_hashes: Mapping[str, str], trigger: TriggerRecord, signal: str, routing: Mapping[str, Any], verdicts: Sequence[PipelineVerdict], evidence: Mapping[str, Mapping[str, Any]], h_struct: Mapping[str, Any], fused: FusedVerdict, gate_outcome: str) -> dict[str, Any]` — fields of design §5.1; `steps` in order `T`, `R`, `P:dpipe`, `P:gpipe`, `P:lpipe`, `F`, `G`; each `P:` step has `items` (§5.2) and `refs` (verdict decision hash; evidence row ref).
- Item extraction: D from `coe_evidence.services` (`D:<svc>:shift|score|final`); G from the stored G-pipe evidence suspects' features (`G:<svc>:<feature>`); L from the L-pipe evidence digests (`L:<worker>:<line_id>`, real names) plus each worker's claims (`L:<worker>:claim<n>`, with `cites`).

- [ ] **Step 1: tests:** `test_steps_in_order_with_unique_ids`; `test_soft_cap_keeps_claims_and_cited_lines` (Review Focus 2: 40 L lines, a claim citing line 38 → line 38 kept, uncited extras trimmed to the cap); `test_refs_match_rows`; `test_no_fused_list_still_builds` (Review Focus 1); `test_entry_has_no_ground_truth_keys`; `test_deterministic` (same inputs → equal entry, timing fields excluded from comparison).
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.

### Task 5: Runner wiring

**Files:** Modify `helios/orchestrator/runner.py` (`coe_path: Path | None = None` → default `<db_path stem>.coe.jsonl`; `coe_signer: Ed25519PrivateKey | None = None` (the Ed25519 private key); confirmatory refusal in `_trigger_for`; store D-pipe `coe_evidence` as `evidence_row` `dpipe`; routing record {ran, gate_value}; build and append the entry in the PASS branch), `bin/helios_run.py` (load the key from `DEVIATION_ED25519_PRIVATE_KEY` when set); Test `tests/test_runner_coe.py`.

- [ ] **Step 1: tests:** `test_full_run_appends_one_coe_entry_per_stored_run` (staged OTel capture, FakeClient); `test_coe_items_cover_all_three_pipelines`; `test_excluded_run_has_no_coe_entry`; `test_no_llm_variant_entry_has_no_l_items` (Review Focus 4); `test_confirmatory_without_key_is_refused`; `test_dpipe_evidence_row_stored`.
- [ ] **Step 2–4:** FAIL → implement → PASS; full suite + CI simulation; commit.

### Task 6: Verification tool and leakage test

**Files:** Modify `bin/verify_ledgers.py` (`--coe <dir>`: each `*.coe.jsonl` → HMAC `verify()` and `verify_public(from_entry=None)`), `tests/evaluation/test_no_ground_truth_leak.py`; Test `tests/test_verify_ledgers_coe.py`.

- [ ] **Step 1: tests:** `test_verify_ledgers_coe_ok_and_tampered`; `test_unsigned_coe_reported_unsigned`; leakage: a staged OTel run's CoE file contains no FAULTS flag name, no label key (`root_cause`, `fault`, `inject`), no injection time.
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.

### Task 7: Deviation entry, docs, close

- [ ] **Step 1:** Draft the entry (C-a, C-b, schema, IDs, soft cap, D-pipe `coe_evidence`, key reuse and confirmatory refusal, unsigned anchors elsewhere, file location, excluded runs). **Owner signs**; CLI → verify → verify-public → ledgers → tests; mirror; commit.
- [ ] **Step 2:** Design §10 (what was built, test evidence); row DONE (parsed); full local gate; CI simulation; fresh whole-branch review; fixes test-first; owner go-ahead → local merge.
