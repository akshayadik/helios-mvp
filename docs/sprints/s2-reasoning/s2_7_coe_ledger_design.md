# S2.7 — Chain-of-Evidence ledger · design

**Task:** S2.7 (tracking S2-M7-ENG07) · **Date:** 2026-10-31 · **Status:** approved 2026-10-31; built (§10), deviation entry 64 · **Depends on:** S2.5 (fusion_row, frozen MAHC, entries 60–63), S2.4 (H_struct), S2.3 (L-pipe evidence), S2.2 (G-pipe evidence), the HMAC-chained anchored ledgers (S0) and the deviation log's Ed25519 layer (entry 35) · **Owner decisions:** marked *owner* (2026-10-31)

**Flag:** the ledger is audit infrastructure and is written for every variant (like the reconciliation ledger); `VCLFlag.COE_NARRATIVE` gates only the narrator (S2.8), never the ledger.

## 1. Intent

Ch3 gives the Chain-of-Evidence (CoE) three roles: the system's decision audit trail; the place routing fallbacks and similar decisions are recorded "as first-class CoE entries"; and the source the Narrative Engine "renders into human-readable form". Today every decision of a run is stored (trigger, verdicts and their decision hashes, G-pipe and L-pipe evidence rows, the fusion row, H_struct, the reconciliation outcome) but nothing ties them into one verifiable record, and D-pipe — often the deciding vote — keeps no evidence at all, so the narrator could not cite why D-pipe ranked a service.

S2.7 builds one signed, append-only CoE entry per incident run: every decision in order, every piece of evidence behind it under a stable ID, so S2.8's narrator cites one record and its grounding verifier checks against it; and so an examiner can verify the whole confirmatory decision trail with the public key alone.

## 2. Decisions already made

| # | Decision | Who |
|---|---|---|
| C-a | **HMAC on every entry, Ed25519 at the end:** entries are HMAC-chained (cheap, streaming); after each incident run the anchor — entry count and the SHA-256 of the whole file — is Ed25519-signed, as in the deviation log (entry 35), so `verify-public` checks every byte with the public key only. No per-entry Ed25519 signature | owner, 2026-10-31 |
| C-b | **One evidence namespace across the pipelines; the CoE is the single citation source** for the S2.8 narrator and its grounding verifier. D-pipe gains an evidence record (a new output; its ranking is frozen and unchanged) | owner, 2026-10-31 |

## 3. Goals, non-goals, anti-goals

**Goals.** A `CoELedger` (HMAC chain + signed anchor with Ed25519); one entry per incident run with the ordered decisions and the cited evidence; D-pipe evidence; the unified evidence-ID scheme; `verify` and `verify-public` for CoE files; the runner writes the entry for every run whose verdicts are stored; tamper tests.

**Non-goals.** The narrator and the verifier (S2.8); rendering; changing any frozen pipeline's ranking or parameters; storing raw telemetry in the ledger.

**Anti-goals** — it fails even if it runs:

- A ground-truth field, fault label (OTel flag names, RCAEval case names) or injection time in a CoE entry. Real service names are expected (the ledger records output; the S2.8 narrator, which reads it, sees real names too).
- An entry that cites evidence the stored rows do not hold (the ledger must be reconstructible from the store).
- A confirmatory run that writes entries it cannot sign.
- Editing, truncating or reordering a ledger passing `verify-public`.

## 4. Constraints

- Reuse `helios/vcl/hmac_chain.py` (`HMACChainedLog`, anchors) and the Ed25519 layer; same project key pair (`keys/deviation_log_ed25519.pub.pem`, `DEVIATION_ED25519_PRIVATE_KEY`) *(my call: one key to back up, one public key in the OSF deposit)*.
- One CoE file per orchestrator run, next to the results database (not in the repository root, not committed); for confirmatory runs it goes into the OSF deposit; real ledgers are verified offline with `bin/verify_ledgers.py --coe <dir>`; CI verifies CoE files only in tests *(my call)*.
- Written only for runs whose verdicts are stored (integrity gate passed), like H_struct and the fusion row; an excluded run gets no CoE entry (its exclusion is in the exclusion and reconciliation ledgers).
- Deterministic content: canonical JSON; timing fields (latency, TTT) are recorded but marked as measured, outside rerun equality.
- Never edit an `.anchor.json` by hand; the CoE anchor is written only by the ledger class.

## 5. Design

### 5.1 One entry per incident run

Fields (canonical JSON): `run_id`, `incident_id` (opaque), `variant_config_hash`, `snapshot_hash`, `evaluation_phase`, `parameter_hashes` (detector, D-pipe, G-pipe, L-pipe prompts and model digest, MAHC), and `steps`, an ordered list:

| Step ID | Decision | Content |
|---|---|---|
| `T` | Trigger | source (threshold / fallback / external), trigger time, suspects, context, signal type |
| `R` | Routing | whether G-pipe ran and the gate value that decided it |
| `P:dpipe`, `P:gpipe`, `P:lpipe` | Each pipeline's verdict | status, ranked list, μ, σ, decision hash, cost, and its evidence items (5.2); for L-pipe also each worker's validity and drop reason, and the H_struct counts |
| `F` | Fusion | method (MAHC or vote-only), weights, priors and level, features, confidence, state, first and terminal publication, disagreeing pipelines |
| `G` | Integrity gate | outcome |

Each step also carries `refs`: SHA-256 of the stored rows it summarises (verdict rows, evidence rows, the fusion row), so the entry can be checked against the store.

### 5.2 Evidence items and IDs

Every citable fact is an item `{id, service, text, value}`, with IDs stable within the entry:

- **D-pipe:** `D:<service>:<signal>` — the per-service components D-pipe already computes before its final score (error, latency and resource shifts after the trigger, and the propagation adjustment), for the services it ranks (top 5) *(my call: top 5 bounds the size)*.
- **G-pipe:** `G:<service>:<feature>` — its stored per-suspect features (wait share, leads, ghost edges, self-time shift).
- **L-pipe:** `L:<worker>:<line>` — the digest lines the workers saw (e.g. `L:log:L12`), with real names (unmasked), and each worker's claims with their cited line IDs.
- **Decisions:** `T`, `R`, `F`, `G` as above.

Text is short and factual (no prose); values are the stored numbers. Items are capped per pipeline *(my call: 30)*, but the cap is soft: every worker claim and every line any claim cites is always kept; the cap trims only uncited extras. The narrator may cite only items present in the entry. The full rows stay in the store, referenced by hash.

### 5.3 Ledger and verification

- `CoELedger(HMACChainedLog)`: `LOG_KIND = "coe"`, `REQUIRED_FIELDS` = the entry fields above, Ed25519 anchor signing from the first entry.
- After each appended entry the anchor is rewritten and Ed25519-signed (one signature per incident run; negligible cost).
- `bin/verify_ledgers.py` and a `verify-public` path cover CoE files: HMAC chain (with the secret), signed anchor and file digest (public key only).
- A confirmatory run without the Ed25519 private key is refused with the other confirmatory refusals (`_trigger_for`). Other runs sign the anchor when the key is present; otherwise the anchor is marked unsigned and `verify-public` reports it as unsigned, never as verified *(my call: existing tests and CI need no private key)*.
- The anchor-only Ed25519 mode is a new opt-in option of the shared ledger module: the deviation log keeps its per-entry Ed25519 signatures (entry 35) unchanged; regression tests run `verify-public` on the real deviation log.

### 5.4 D-pipe evidence

`run_dpipe` returns a `coe_evidence` field (a distinct name: its internal `evidence` dict feeds sigma and must not change), per ranked service the component scores it already computes; the runner stores it as an `evidence_row` with pipeline `dpipe`, which the CoE `refs` point to. The ranking, μ, σ and every frozen parameter are unchanged; a test pins D-pipe's ranked list and decision hash on build fixtures before and after.

## 6. Protocol records

- **Deviation entry** before merge: C-a, C-b, the entry schema, the ID scheme, D-pipe's new evidence output (no change to its ranking), the key reuse, and that excluded runs get no CoE entry. Owner reviews, then signs.

## 6a. Size and tracking

The plan gives S2.7 1 day; with D-pipe evidence and the ID scheme, my estimate is **2**. Row S2-M7-ENG07. One PR (no build run, nothing to freeze).

## 7. Done when

- The ledger verifies (HMAC chain and Ed25519 anchor); `verify-public` passes with the public key only.
- Tamper tests: an edited entry, a removed entry, a reordered pair and a truncated file each fail verification.
- Every CoE item's ID is unique in its entry, and every `refs` hash matches the stored row.
- D-pipe's ranked list and decision hash unchanged on build fixtures.
- No ground-truth field, fault label or injection time in any entry (the leakage test compares entries with the ground-truth values).
- A confirmatory run without the Ed25519 private key is refused before any incident; an unsigned anchor is reported as unsigned.
- The deviation log still passes `verify-public` (regression).

## 8. Calls I made (owner to check)

1. **Same Ed25519 key pair** as the deviation log.
2. **One CoE file per orchestrator run**, beside the reconciliation ledger.
3. **D-pipe evidence for its top 5 services;** at most 30 items per pipeline in an entry.
4. **Excluded runs get no CoE entry** (as H_struct and fusion rows).
5. **Timing fields recorded but outside rerun equality.**
6. **Refs are SHA-256 of the stored rows'** canonical JSON.
7. **Key required only for confirmatory runs;** other runs sign if the key is present, else the anchor is marked unsigned.
8. **CoE files beside the results database,** in the OSF deposit for confirmatory runs, verified offline.
9. **Soft item cap:** claims and their cited lines always kept.
10. **D-pipe's new output is `coe_evidence`,** stored as an `evidence_row` (pipeline `dpipe`).
11. **Anchor-only Ed25519 is an opt-in mode;** the deviation log is unchanged and regression-tested.

## 9. Left to the builder

Exact item text wording; which D-pipe intermediate fields map to which signal names; the CoE file name convention; how `verify_ledgers.py` discovers CoE files.

## 10. Results

Built 2026-10-31 on branch `s2/coe` (commits `57c5584`..`90f38aa`); deviation entry 64 (`d5f859b4c98aca08`).

**What was built**

| Part | Where | Notes |
|---|---|---|
| Anchor-only Ed25519 mode | `helios/vcl/hmac_chain.py` (`ANCHOR_ED25519`, `check_append`, `verify_public(from_entry=None)`) | Opt-in; the deviation log is unchanged (regression test on the real log: 64 entries, 30 Ed25519-signed) |
| `CoELedger`, entry builder | `helios/orchestrator/coe.py` (`build_coe_entry`, `row_ref`, `fusion_record`, `ITEM_CAP = 30`) | Steps T, R, P:dpipe, P:gpipe, P:lpipe, F, G; items `{id, service, text, value}` (claims add `cites`) |
| D-pipe evidence | `run_dpipe` → `coe_evidence`; `ScoredServices.channels` | Top 5: error, latency and resource shifts (robust units), pre-propagation score, final score; stored as an `evidence_row` (pipeline `dpipe`) |
| Runner wiring | `helios/orchestrator/runner.py` | One file per orchestrator run: `<db stem>.coe/<UTC start>-<8 hex>.coe.jsonl` (gitignored); pre-flight `check_append` in `run()`; entry built before any store write, appended after; confirmatory runs refuse without the key |
| Verification | `bin/verify_ledgers.py --coe DIR [--public-only] [--public-key PATH]` | HMAC chain plus signed anchor; `--public-only` needs no secret |
| CLI key | `bin/helios_run.py` | `DEVIATION_ED25519_PRIVATE_KEY` checked against the committed public key |

**Builder's calls (§9)**

- D-pipe items: `D:<svc>:error|latency|resource` (omitted when no usable trigger split), `D:<svc>:propagation` (final minus pre-propagation score, only when non-zero), `D:<svc>:score`, `D:<svc>:final`: at most six per service, thirty for the top 5.
- G-pipe items skip empty `wait_from`, `leads` and `ghost_edges` (`self_shift` always).
- L-pipe items: lines and claims per worker in worker-name order; the raw model text and worker wall time stay in the evidence row (referenced by hash), not in the entry. A cite that is not a digest line of that worker is dropped from `cites`.
- Routing record `R`: `ran`, `gate_value` (only where routing evaluates the gate), `threshold`, `reason` (`gpipe_off`, `no_graph`, `below_gate`, `routed`).
- `refs`: each pipeline step's verdict decision hash (checkable against `result_row.decision_hash`) and SHA-256 of the canonical stored evidence and fusion rows. The fusion ref and the schedule-derived F fields (state, first ranking, non-convergence) follow the replayed timing, as the stored fusion row does; latency, CPU and publication times sit under `measured`.

**Whole-branch review (fresh reviewer): 0 Critical, 4 Important, all fixed test-first**

1. *Signature downgrade and laundering:* a holder of the HMAC secret alone could cut entries, write an unsigned anchor, and have the owner's next keyed run sign the edited file. Fixed by monotonic signing per file (a keyless append onto a signed file and a keyed append onto a non-empty unsigned file are refused) and one file per orchestrator run (§4). This reverses the plan's Review Focus 5 ("unsigned then keyed append verifies"), which was the laundering path.
2. *No public-key-only check:* `--public-only` added.
3. *Rows stored without their entry on a builder or ledger error:* pre-flight in `run()`; entry built before the inserts.
4. *D-pipe shift not split by signal (§5.2):* per-channel shifts and the propagation adjustment added; ranking unchanged.

A fifth finding (the routing gate evaluated for every variant, and it raises on negative scores) was re-graded Important and fixed. Six minors are deferred (see the review ledger): timing-dependent fusion ref (documented above), decision hash as the verdict ref, evidence-presence predicate (latent), dropped invalid cites, `anchor_unsigned` popped for every ledger kind, model-digest fallback.

**Test evidence**

- D-pipe ranked list, μ, σ and decision hash on two OTel build windows recorded before the change and unchanged after (`tests/pipelines/d_pipe/test_coe_evidence.py`).
- Tamper tests: edited, removed, reordered and truncated entries each fail `verify()` and `verify_public`; downgrade-then-launder refused; unsigned anchors reported unsigned (`tests/test_coe_ledger.py`).
- Builder: step order, unique IDs, soft cap (a claim citing line 38 of 40 keeps it; 35 claims keep all 35 cited lines), refs, no fused list, determinism outside `measured` (`tests/test_coe_entry.py`).
- Runner: one entry per stored run with refs matching the stored rows, G items when routed, below-gate record, excluded run gives no entry, noLLM has no `L:` items, HELIOS-D never evaluates the gate, confirmatory refusal without the key, pre-flight and build-before-store (`tests/test_runner_coe.py`).
- Leakage: no fault flag name, case name, label key or injection time in a staged run's CoE file; mutation-checked (`tests/evaluation/test_no_ground_truth_leak.py`).
- Full suite green, coverage 95.90%.
