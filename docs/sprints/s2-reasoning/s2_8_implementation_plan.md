# S2.8 Narrative Engine with grounding verifier — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every run with `coe_narrative` on gets a narrative (header, story, contradictions, verification) whose every displayed claim cites a CoE item that exists and supports it; noLLM, D and G narrate from a deterministic template, the other variants from the frozen 8B model behind the same verifier.

**Flag:** `VCLFlag.COE_NARRATIVE` gates the engine (off = ranked list only); `l2c_llm` picks the narrator (on = LLM, off = template).

**Architecture:** A new package `helios/narrative/` reads one CoE entry (S2.7) and nothing else. Both narrators emit the same typed claims; one pure verifier checks each claim against the entry; one renderer turns accepted claims into text. The LLM narrator calls the model once per slot through L-pipe's gateway and response cache, retries a rejected slot once, then falls back to the template's slot. The runner adds the narrative to the CoE entry as step `N` before appending, and stores a `narrative_row`.

**Tech Stack:** Python 3.11, pydantic v2, duckdb, Ollama (llama3.1:8b via `helios/pipelines/l_pipe/ollama_client.py`, `gateway.py`, `cache.py`); pytest.

**Spec:** `docs/sprints/s2-reasoning/s2_8_narrator_design.md` (approved 2026-10-31; decisions N-a…N-i, §5.8 builder answers). Row **S2-M7-ENG08**.

## Global Constraints

- N-a: no model call when `l2c_llm` is off — noLLM, D and G narrate only from the template.
- Every displayed claim was accepted by the verifier and cites at least one ID present in the entry; a slot is all-LLM or all-template (N-d).
- Citable: `D:<svc>:<channel>` (shift), `D:<svc>:score|propagation|final` (ranking only), `G:*`, `L:<worker>:<line>`, step `F`; never `L:<worker>:claim<n>`.
- Containment (N-b): only the claim's services named (caller and callee for call-structure); every number in a cited item after normalisation (N-f: percent ↔ fraction, ms ↔ s, "~"/"about", ±1% relative or the stated precision); direction words agree.
- Verification steps (N-g): target in fused top-3 or caller/callee via a cited G edge; times inside `[T.window_start, T.window_end]`; verb in the frozen list (query, inspect, verify, check, filter); modality matches the cited item; ≥1 cite.
- Retry: one per slot at the pinned temperature with the rejection reasons; then the template slot and a fallback event.
- The narrator never changes ranking, μ, σ, confidence or state; the header is filled by code from `F`.
- Narrator tokens count in CpR (step `N` `cost`); narrator wall time under `measured`, outside TTT.
- Direction words, verbs and tolerance live in `data/frozen/narrator_params.json` (`provisional: true` until entry C); provisional prompt or parameters are refused in confirmatory runs.
- D-pipe ranking, μ, σ and decision hash unchanged (golden test from S2.7 stays green).
- Never read pool data; prompt rounds on the build dev split, judged by the verification report only.
- Never edit `metric_contract.md`, `research/osf/*`, `variants.py`, any `.anchor.json`; deviation entries via the CLI after owner approval; never `cd`; never `git commit -a`; check exit codes; full local gate; local `--no-ff` merge on the owner's go-ahead; no push.

## Review Focus

1. **Numbers that are not facts** — citation IDs (`L12`), ranks ("top-3", "#2"), wall-clock times ("14:52") and window offsets must not be checked as evidence numbers, or valid sentences are rejected. *(Task 4 test)*
2. **Service names that are substrings or common words** (`cart` in `cartservice`, `ad`) — foreign-service detection uses token matching (reuse `helios/pipelines/l_pipe/aliases.py`'s matcher), not substring search. *(Task 4 test)*
3. **Model unreachable or returning junk** (connection error, non-JSON, JSON that is not a claim list, unknown kind) — the slot falls back to the template, the run completes, the event is logged. *(Task 6 test)*
4. **A run with no fused ranking and no evidence** (every pipeline abstained) — template header only, no model call, entry still verifies. *(Task 5 and Task 7 tests)*
5. **RCAEval windows without a usable trigger split** — D channel items have no raw levels; the template and verifier still work, and no unit is invented. *(Task 2 and Task 5 tests)*

---

## PR 1 — engine, verifier, storage (branch `s2/narrator`)

### Task 1: Open the row

- [ ] Branch `s2/narrator` from local `main`; commit the design note and this plan; row S2-M7-ENG08 IN_PROGRESS (Started 2026-10-31, Deps S2-M7-ENG07) in its own commit; `python3 scripts/validate_tracking.py` exit 0.

### Task 2: Raw before/after levels in D-pipe evidence (N-i) and window bounds in the CoE `T` step

**Files:** Modify `helios/pipelines/d_pipe/stages/b_anomaly_scorer.py` (`ScoredServices.levels`), `helios/pipelines/d_pipe/pipeline.py` (`coe_evidence`), `helios/orchestrator/coe.py` (`_dpipe_items`, `build_coe_entry`), `helios/orchestrator/runner.py` (pass bounds); Test `tests/pipelines/d_pipe/test_coe_evidence.py`, `tests/test_coe_entry.py`.

**Interfaces — Produces:**
- `ScoredServices.levels: dict[str, dict[str, dict[str, float | str]]]` — per service and channel `{"before", "after", "unit"}`: medians of the series before and after the split; resource uses the metric that gave the max shift and its name.
- `UNITS: Mapping[str, str]` in `b_anomaly_scorer.py`: OTel span-metric latency → `"ms"`; error channel → `"errors/step"`; otherwise the metric name.
- `coe_evidence.services[i]` gains `"levels": {channel: {"before", "after", "unit"}}` (channel absent when no split).
- CoE item `D:<svc>:<channel>` gains `"before"`, `"after"`, `"unit"` keys when present.
- `build_coe_entry(..., window_start: str, window_end: str)` → `T` step keys `window_start`, `window_end` (ISO UTC).

- [ ] **Step 1: tests:** `test_levels_before_after_and_unit` (OTel build window 9: cart latency `unit == "ms"`, `after > before` where latency shift > 0); `test_ranking_mu_sigma_and_decision_hash_unchanged` (existing golden test, unchanged); `test_no_split_has_no_levels` (window without a trigger split → no `levels` channels); `test_d_items_carry_levels` and `test_t_step_has_window_bounds` in `test_coe_entry.py`.
- [ ] **Step 2–4:** FAIL → implement → PASS (also `tests/test_runner_coe.py`, leakage test); commit.

### Task 3: Claims, parameters and renderer

**Files:** Create `helios/narrative/__init__.py`, `helios/narrative/claims.py`, `helios/narrative/params.py`, `helios/narrative/render.py`, `data/frozen/narrator_params.json`; Test `tests/narrative/test_claims.py`, `tests/narrative/test_render.py`.

**Interfaces — Produces:**
- `SLOTS = ("story", "contradictions", "verification")`; `ClaimKind` (StrEnum): `shift`, `call_structure`, `log_message`, `ranking`, `contradiction`, `verification_step`.
- `Claim` (frozen pydantic, `extra="forbid"`): `kind`, `sentence: str`, `cites: tuple[str, ...]` (min 1), optional `service`, `channel`, `direction` (`up`/`down`), `caller`, `callee`, `feature` (`wait`/`lead`/`ghost`), `snippet`, `rank: int`, `pipeline`, `target_service`, `action_verb`, `modality` (`metric`/`log`/`edge`), `window_start`, `window_end`.
- `parse_slot(raw: str) -> list[Claim]` raising `ClaimSchemaError` on non-JSON, non-list (`{"claims": [...]}` accepted), unknown kind or missing kind-required fields (table in design §5.2).
- `NarratorParams` (frozen): `direction_words: dict[str, tuple[str, ...]]`, `verbs: tuple[str, ...]`, `rel_tolerance: float`, `max_steps: int = 3`, `provisional: bool`; `load_narrator_params(path=...)`, `narrator_params_hash(p) -> str`.
- `render(entry: Mapping[str, Any], slots: Mapping[str, Sequence[Claim]]) -> str` — header from `F` (top-3, confidence, state) then each slot's sentences with `[ID, ID]` citation suffixes; one renderer for both narrators.

- [ ] **Step 1: tests:** `test_parse_accepts_list_and_wrapped`; `test_parse_rejects_unknown_kind_missing_fields_and_non_json` (each raises `ClaimSchemaError`); `test_params_file_is_provisional_and_hash_stable`; `test_render_header_from_f_only` (header equals F's top-3; a claim cannot alter it); `test_render_same_shape_for_both_sources` (rendering ignores who wrote the claims).
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.

### Task 4: Verifier

**Files:** Create `helios/narrative/verifier.py`; Test `tests/narrative/test_verifier.py`.

**Interfaces — Consumes:** Task 3 `Claim`, `NarratorParams`; CoE entry shape (S2.7 + Task 2).
**Produces:** `Reason` (StrEnum, the closed set of design §5.5: `missing_cite`, `unknown_id`, `kind_mismatch`, `wrong_direction`, `wrong_edge`, `snippet_not_found`, `foreign_service`, `number_not_in_evidence`, `time_out_of_window`, `verb_not_allowed`, `modality_mismatch`, `rank_mismatch`, `not_in_disagree`, `schema`); `verify(claim: Claim, entry: Mapping[str, Any], params: NarratorParams) -> Reason | None` (None = accepted); `entry_services(entry) -> set[str]`.

Numbers: extract numeric tokens from the sentence after removing citation IDs, rank expressions (`top-N`, `#N`, ordinals), and wall-clock times (checked separately against the window); normalise percent and ms/s by the cited item's unit; accept if any cited item's `value`, `before` or `after` matches within `rel_tolerance` or the sentence's stated precision.

- [ ] **Step 1: tests** (one per reason, each on a hand-built entry): `test_accepts_supported_claim_of_each_kind`; `test_unknown_id_and_worker_claim_not_citable`; `test_wrong_direction_word` ("fell" with `direction=up`); `test_wrong_edge_inverted_caller_callee`; `test_snippet_must_be_verbatim`; `test_foreign_service_token_match` (Review Focus 2: "cartservice" ≠ "cart"; "ad" as a word); `test_numbers_normalised` ("94%" vs 0.94, "1.4 s" vs 1420 ms, "~120 ms"); `test_ids_ranks_and_times_are_not_evidence_numbers` (Review Focus 1); `test_number_not_in_evidence`; `test_time_out_of_window`; `test_verb_and_modality` ; `test_rank_mismatch`; `test_not_in_disagree`; `test_ranking_claim_may_cite_score_items_shift_may_not`.
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.

### Task 5: Template narrator

**Files:** Create `helios/narrative/template.py`; Test `tests/narrative/test_template.py`.

**Interfaces — Produces:** `template_slots(entry: Mapping[str, Any], params: NarratorParams) -> dict[str, list[Claim]]` (design §5.3; story for suspects 1–3; one contradiction per `F.disagree`; ≤ `max_steps` verification steps, window = `T` bounds).

- [ ] **Step 1: tests:** `test_template_passes_verifier_on_every_build_case` (build CoE entries from both corpora via a staged run fixture; every claim `verify(...) is None`); `test_template_is_deterministic`; `test_empty_entry_gives_empty_slots` (Review Focus 4); `test_no_levels_no_invented_unit` (Review Focus 5); `test_one_contradiction_per_disagreeing_pipeline`.
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.

### Task 6: LLM narrator with retry and fallback

**Files:** Create `helios/narrative/llm.py`, `helios/narrative/prompt.py` (round-1 prompt text, `NARRATOR_PROMPT_SHA` computed, `PROVISIONAL = True`); Test `tests/narrative/test_llm.py`.

**Interfaces — Consumes:** Tasks 3–5; `LLMGateway`, `ResponseCache`, `cache_key` from L-pipe.
**Produces:**
- `SlotResult` (frozen): `source` (`llm`/`template`), `claims: tuple[Claim, ...]`, `attempts: int`, `rejections: tuple[tuple[int, str], ...]` (claim index, reason) per attempt, `fallback: bool`.
- `llm_slots(entry, params, *, gateway: LLMGateway, cache: ResponseCache | None, model_digest: str) -> dict[str, SlotResult]` — per slot: skip (empty, no call) when the template slot is empty; else prompt → parse → verify all → on any rejection or `ClaimSchemaError` or model error, one retry with reasons → else template slot, `fallback=True`.
- `render_prompt(slot: str, entry, header, rejections=None) -> str`.

- [ ] **Step 1: tests** with a scripted fake client: `test_accepted_first_pass`; `test_retry_then_accept_counts_two_calls`; `test_two_failures_fall_back_to_template_slot`; `test_model_error_and_junk_fall_back` (connection error, non-JSON, wrong shape — Review Focus 3); `test_cache_replays_retry_deterministically` (second run: zero model calls, identical result, usage replayed); `test_empty_slot_makes_no_call`.
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.

### Task 7: Engine, storage, CoE step N, runner wiring

**Files:** Create `helios/narrative/engine.py`; Modify `helios/store/schema.sql` (`narrative_row`, tag `narrative-v1`), `helios/store/result_store.py` (`insert_narrative`, `fetch_narrative`, `fetch_all_narrative_rows`), `helios/orchestrator/runner.py`; Test `tests/narrative/test_engine.py`, `tests/test_runner_narrative.py`.

**Interfaces — Produces:**
- `Narrative` (frozen): `narrator` (`llm`/`template`), `slots: dict[str, SlotResult]`, `rendered: str`, `prompt_tokens`, `completion_tokens`, `wall_ms`; `as_step() -> dict` = `{"id": "N", "narrator", "slots", "rendered", "cost": {...}, "measured": {"wall_ms"}}`.
- `run_narrative(entry, *, params, llm: bool, gateway, cache, model_digest) -> Narrative`, decorated `@gated_by(VCLFlag.COE_NARRATIVE)`.
- `helios/evaluation/cost.py`: `incident_usage(verdicts, *, storage_bytes=0, narrative: Mapping[str, Any] | None = None)` adds the stored narrative row's prompt and completion tokens (design §4: narrator tokens count in CpR); every caller that has a run's `narrative_row` passes it.
- Runner: after `build_coe_entry` and before any insert: `run_narrative` (skipped when gated off) → `entry["steps"].append(narrative.as_step())`; `insert_narrative` with the other rows; confirmatory refusal when narrator prompt or params are provisional and `coe_narrative` is on.

- [ ] **Step 1: tests:** `test_full_run_has_llm_narrative_in_coe_entry` (FakeClient; step N present; ledger verifies); `test_nollm_d_g_make_no_model_call` (a client that fails on any call; narrator `template`); `test_noexpl_has_no_narrative`; `test_llm_only_narrates_with_llm`; `test_fused_and_verdict_rows_unchanged_by_narrator` (decision hashes and fusion row equal with `coe_narrative` on and off); `test_every_displayed_claim_verified_and_cited` (stored row: every claim in a displayed slot re-verifies against the stored entry); `test_all_abstained_run_template_header_only` (Review Focus 4); `test_confirmatory_refuses_provisional_narrator`; `test_cpr_counts_narrator_tokens` (`incident_usage` with a narrative row adds its tokens; without one, unchanged); leakage test extended to the rendered narrative.
- [ ] **Step 2–4:** FAIL → implement → PASS; full suite; commit.

### Task 8: Verification report

**Files:** Create `helios/evaluation/narrative_report.py`; Test `tests/evaluation/test_narrative_report.py`.

**Interfaces — Produces:** `narrative_report(rows: Sequence[Mapping[str, Any]]) -> dict` per narrator: claims, first-pass acceptance rate, rejections by reason, retry success, slot fallback rate, sentence-length and claims-per-slot distributions (design §5.8 style check). No ground truth read.

- [ ] **Step 1: tests:** `test_report_counts_and_rates` (fixture rows); `test_report_reads_no_ground_truth` (signature and source scan as in the leakage test).
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.

### Task 9: Entries A and B, docs, close PR 1

- [ ] **Step 1:** Draft entry A (H_fact definition, N-e) and entry B (narrator rules, additive CoE fields, params file); **owner reviews and approves**; sign via the CLI; `verify`, `verify-public`, `verify_ledgers`; mirror both in `docs/tracking/deviation_log.md`; register count; commit.
- [ ] **Step 2:** Backlog: mark S2-BL-15 resolved by N-a; full local gate; fresh whole-branch review (most capable model) with the Review Focus; fixes test-first; owner go-ahead → local `--no-ff` merge.

## PR 2 — prompt round and freeze (branch `s2/narrator-freeze`)

### Task 10: Build tool and rounds

**Files:** Create `bin/narrator_build_run.py`; Test `tests/test_narrator_build_run.py`.

**Interfaces — Produces:** `--round N` (dev split from `split_cases`), `--final` (held-out); runs HELIOS-Full and HELIOS-noLLM over both build corpora through `RunOrchestrator` with the real Ollama client and the shared cache (L-pipe calls are cache hits); writes `docs/sprints/s2-reasoning/calibration/narrator_round<N>.json` = `narrative_report` per narrator and corpus; refuses `--final` before a round is chosen.

- [ ] **Step 1: tests:** `test_round_uses_dev_split_only`; `test_report_written_without_ground_truth`; `test_final_requires_chosen_round` (fake client, two staged cases).
- [ ] **Step 2–4:** FAIL → implement → PASS; commit.
- [ ] **Step 5:** Round 1 on the dev split (expect several hours: up to 3 calls per case); bring the report to the owner; at most 3 rounds, prompt edits between rounds recorded; owner chooses.

### Task 11: Freeze and close

- [ ] **Step 1:** `--final` on the held-out split; freeze `NARRATOR_PROMPT_SHA` (`PROVISIONAL = False`) and `narrator_params.json` (`provisional: false`); draft entry C (round chosen, report figures, hashes); **owner approves**; sign; mirror.
- [ ] **Step 2:** Design §10; row DONE; full gate; fresh review; owner go-ahead → local merge.
