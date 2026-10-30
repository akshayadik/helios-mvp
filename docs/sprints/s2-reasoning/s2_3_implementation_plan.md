# S2.3 Lean multi-agent L-pipe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L-pipe ranks root-cause candidates from raw telemetry through three single-modality workers (metric, log, trace) over deterministic, aliased digests, merged by deterministic code into (μ, σ), independent of D-pipe and G-pipe.

**Architecture:** New modules in `helios/pipelines/l_pipe/`: `aliases.py` (alias map, masking, leak check), `digests.py` (three digest builders, cap), `personas.py` (profiles, prompts, SHAs), `workers.py` (one call + validation), `merge.py` (equal-weight Borda, μ, σ), `cache.py` (response cache). `pipeline.py`'s `run_lpipe` is rewritten on top; the runner passes window and trigger. Build runs in `helios/evaluation/lpipe_calibration.py` + `bin/lpipe_build_run.py`. PR 1 builds everything with provisional prompts and records the rules; PR 2 runs build data, revises prompts (≤ 3 rounds), freezes.

**Tech Stack:** Python 3.11, pandas, numpy, pydantic v2, requests (Ollama), drain3 (existing), sqlite3 (cache); pytest.

**Spec:** `docs/sprints/s2-reasoning/s2_3_lpipe_design.md` (approved 2026-10-30). Tracking row **S2-M7-ENG03**.

## Global Constraints

- L-pipe never reads D-pipe or G-pipe output, the UEG-C, labels, fault names or injection time (L-a, L-e). Candidates = in-scope services of the window from `helios.telemetry.trigger.service_scores(...).services` filtered by `helios.telemetry.scope.in_scope` — never the graph (`l2b_graph` is OFF in HELIOS-LLM-only).
- Window split at the frozen trigger's `trigger_time_s`; digest timestamps relative to it ("+90 s").
- Every service and out-of-scope component name is aliased in every prompt (`svc-NN`, `dep-NN`); alias order from a SHA-256 of the incident ID, no seed (L-i). A prompt with a surviving real name is refused.
- Prompts carry **no incident ID at all** (stricter than the design's "opaque ID only"; nothing needs it).
- Worker output: up to `MAX_RANKED = 5` services, each with ≥ 1 claim whose citations all exist in that worker's own digest; else the service is dropped (L-e). One retry on schema failure (`LPIPE_MAX_RETRIES = 1`).
- Merge: rank r scores (6 − r)/5; mean over the k valid workers (1/k each, L-c); ties by alias-free real service name; μ = `top1_share`; σ = 1 − agreement × gap; k = 1 → σ = 1; k = 0 → ABSTAINED, μ and σ None (L-d).
- Trace worker runs only on windows whose P2 format was validated on build data (OTel captures); RCAEval-format windows skip it (L-f). Unknown format → skipped (fail closed).
- Token cap per digest `DIGEST_TOKEN_CAP = 2000`, tokens estimated as ⌈characters / 4⌉; lines ordered by shift size, cut count recorded.
- Protocol A unchanged; model `llama3.1:8b`; calls strictly sequential; `TIMEOUT_S` (120 s) only catches hangs (L-g); every drop recorded.
- Cache key = (model digest, prompt SHA, rendered-prompt SHA); a hit replays usage **and** wall time; verdict records `cache_hit`.
- Build data only: `otel_build_v3` (63) and `rcaeval_build` (495; 120 with logs, none with traces). Pool refused before tag `build-freeze`; tool output aggregates only.
- Every new module references the VCL (flag-guard); L-pipe stays under `VCLFlag.L2C_LLM`; no new flag; never edit `helios/vcl/variants.py`, `research/osf/*`, `docs/tracking/metric_contract.md`, the seed register, `TelemetryWindow`.
- Deviation entries via the CLI only, signed after owner review; tracking rows IN_PROGRESS → DONE in separate commits; never `cd`; never `git commit -a`; check the pytest exit code before any commit; full gate before each PR; the owner merges.

## Review Focus

1. **Fault names inside telemetry** — OTel services can log feature-flag names (`paymentFailure`, `adServiceHighCpu`) that are the fault labels. Expected: masked like component names (`flag-NN`) from a static list in `aliases.py`, which a test checks equals the campaign's fault catalogue. *(Task 2 test)*
2. **Short service stems** — `ad` must mask `AdService`, `adservice`, `ad-service`, `ad:9555` but not `address`, `load`, `header`. Expected: matching on token and camelCase boundaries, longest name first (`frontend-proxy` before `frontend`). *(Task 2 test)*
3. **RCAEval logs with empty `severity`** and services with no logs → log digest still built from template counts; a candidate with no lines is simply absent, no crash. *(Task 4 test)*
4. **Model answer naming a real service, an unknown alias, or citing another worker's IDs** (`T3` from the log worker) → that claim is invalid; the service drops if no valid claim remains. *(Task 7 test)*
5. **All workers invalid on a window with candidates** → ABSTAINED verdict with every drop reason; the runner still produces D and G verdicts; no exception escapes `run_lpipe`. *(Task 10 test)*

---

## PR 1 — workers, merge, cache, rules entry

### Task 1: Open the row

- [ ] **Step 1:** Branch `s2/lpipe` from `main`. Commit the design note (`docs(s2.3): L-pipe design, approved 2026-10-30`) and this plan.
- [ ] **Step 2:** Set `S2-M7-ENG03` IN_PROGRESS (Started 2026-10-30), mutable columns only; `poetry run python scripts/validate_tracking.py` → exit 0; commit `tracking: S2-M7-ENG03 IN_PROGRESS (S2.3 L-pipe)`.

### Task 2: Alias map and masking

**Files:** Create `helios/pipelines/l_pipe/aliases.py`; Test `tests/pipelines/l_pipe/test_aliases.py`.

**Interfaces — Produces:**
- `class AliasLeakError(RuntimeError)`.
- `FEATURE_FLAG_NAMES: frozenset[str]` — the OTel demo's flagd fault flags (static).
- `@dataclass(frozen=True) class AliasMap`: `forward: Mapping[str, str]` (real → alias), `backward: Mapping[str, str]`; methods `mask(text: str) -> str`, `unmask(alias: str) -> str`, `check(text: str) -> None` (raises `AliasLeakError` naming no real name in its message, only a count).
- `build_alias_map(incident_id: str, candidates: Sequence[str], components: Sequence[str]) -> AliasMap` — candidates → `svc-01…` in the order of SHA-256(`incident_id` + name); components (out-of-scope names seen in the window, plus `FEATURE_FLAG_NAMES`) → `dep-NN` / `flag-NN` likewise.

- [ ] **Step 1: tests:** `test_same_incident_same_map`; `test_different_incidents_differ` (two IDs, 8 candidates → different orders); `test_spelling_variants_masked` (`checkout`, `checkoutservice`, `checkout-service`, `CheckoutService`, `hipstershop.CheckoutService/PlaceOrder`, `http://checkout:8080/api/checkout`, `checkout-7d9f` pod name → no `checkout` left, case-insensitive); `test_short_stem_respects_boundaries` (Review Focus 2); `test_longest_name_first`; `test_components_and_flags_masked` (`redis`, `paymentFailure` → `dep-`, `flag-`); `test_check_refuses_survivor`; `test_flag_list_matches_campaign_catalogue` (test imports the campaign's fault list; the run path does not); `test_unmask_round_trip`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 3: Digest core and metric digest

**Files:** Create `helios/pipelines/l_pipe/digests.py`; Test `tests/pipelines/l_pipe/test_digests.py`.

**Interfaces — Produces:**
- `@dataclass(frozen=True) class DigestLine`: `line_id: str` (`M1`, `L1`, `T1`…), `service: str` (real name), `text: str` (real names; masked at render), `weight: float` (shift size, for ordering).
- `@dataclass(frozen=True) class Digest`: `modality: Literal["metric", "log", "trace"]`, `lines: tuple[DigestLine, ...]`, `cut: int`; `render(alias: AliasMap) -> str` (one line per `"<id> <masked text>"`, then `alias.check`).
- `estimate_tokens(text: str) -> int` = ⌈len / 4⌉; `cap_lines(modality, lines, token_cap) -> Digest` — sort by (−weight, service, text), keep while the rendered total fits, number IDs after sorting.
- `metric_digest(window: TelemetryWindow, trigger: TriggerRecord, candidates: Sequence[str], *, root: Path) -> Digest | None` — per candidate and P1 series (`metric_name` + `labels.service_name`), shift after the trigger in robust units: (median after − median before) / `robust_scale(before, count_series=…)`; series with no scale skipped; top 3 per service; text like `"checkout latency-90 up 6.2 robust units from +60 s"`. None without P1.

- [ ] **Step 1: tests:** `test_cap_keeps_largest_shifts_and_counts_cut`; `test_ids_follow_sorted_order`; `test_metric_shift_exact` (hand frame: before values constant-with-noise, after +k scales → text and weight exact); `test_metric_digest_never_reads_before_window_or_labels` (only P1 path opened); `test_relative_times_only` (no ISO timestamp in any line).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 4: Log digest

**Files:** Modify `helios/pipelines/l_pipe/digests.py`; Test same file.

**Interfaces — Produces:** `log_digest(window, trigger, candidates, *, root: Path) -> Digest | None` — from `features_for_window`: per candidate, templates new after the trigger (from `novelty`/`counts`) and templates whose rate after/before rose most; text `"cart template 'connection to <IP> failed' new after trigger, 41 lines"` / `"… rose 3 → 58 lines"`; weight = after-count for new, ratio for rising; severity appended when non-empty. None without P3.

- [ ] **Step 1: tests:** `test_new_template_after_trigger_listed`; `test_rising_template_listed_with_counts`; `test_empty_severity_and_silent_service` (Review Focus 3); `test_log_digest_deterministic` (twice → equal).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 5: Trace digest and the format gate (L-f)

**Files:** Modify `helios/pipelines/l_pipe/digests.py`; Test same file.

**Interfaces — Produces:**
- `trace_format_validated(window: TelemetryWindow, *, root: Path) -> bool` — True only for OTel-capture windows (decided from the sealed manifest's provenance, e.g. its `schema_version`, without adding a field); RCAEval-adapter windows and anything unrecognised → False.
- `trace_digest(window, trigger, candidates, *, root: Path) -> Digest | None` — None when no P2 or not validated; else from `helios.graph.span_features` (`analyse_spans`, `split_at`): per candidate, error-span counts before/after and status messages, operations whose median latency rose most.

- [ ] **Step 1: tests:** `test_rcaeval_window_not_validated` (an `rcaeval_build` manifest); `test_otel_v3_window_validated`; `test_unknown_format_fails_closed`; `test_trace_digest_errors_and_latency` (hand P2 frame); `test_trace_digest_none_when_not_validated`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 6: Persona Profiles and prompts

**Files:** Create `helios/pipelines/l_pipe/personas.py`, `helios/pipelines/l_pipe/prompts/metric_v1.txt`, `log_v1.txt`, `trace_v1.txt`; Modify `helios/pipelines/l_pipe/lpipe_config.py` (add `WORKER_PROMPT_SHAS: dict[str, str | None]` all None = provisional, `DIGEST_TOKEN_CAP = 2000`, `MAX_RANKED = 5`); Test `tests/pipelines/l_pipe/test_personas.py`.

**Interfaces — Produces:**
- `@dataclass(frozen=True) class PersonaProfile`: `name: Literal["metric", "log", "trace"]`, `stream: Literal["p1", "p3", "p2"]`, `prompt_path: Path`, `build: Callable[..., Digest | None]`.
- `PERSONAS: tuple[PersonaProfile, ...]` in order metric, log, trace.
- `render_prompt(persona, digest: Digest, alias: AliasMap) -> str` — template placeholders `{candidates}` (aliases, sorted), `{digest}`, `{max_ranked}`; output contract in the prompt: `{"ranked": [{"service": "svc-NN", "claims": [{"text": "...", "cites": ["M3"]}]}]}`.
- `prompt_sha(persona) -> str`; `provisional() -> bool` (any SHA None).

- [ ] **Step 1: tests:** `test_each_builder_opens_only_its_stream` (monkeypatch `pd.read_parquet`, record paths; metric → P1 only, log → P3 only, trace → P2 (+ manifest) only); `test_rendered_prompt_has_no_real_names_or_ids` (real OTel v3 build window: no real service, component, flag name, incident ID, data path, ISO timestamp); `test_prompt_files_contain_contract_placeholders`; `test_provisional_until_frozen`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 7: Worker call and validation

**Files:** Create `helios/pipelines/l_pipe/workers.py`; Test `tests/pipelines/l_pipe/test_workers.py`.

**Interfaces — Produces:**
- `class DropReason(StrEnum)`: `NO_DIGEST`, `TIMEOUT`, `CONNECTION`, `HTTP`, `SCHEMA`, `NO_VALID_CLAIM`.
- `@dataclass(frozen=True) class Claim`: `text: str` (unmasked), `cites: tuple[str, ...]`.
- `@dataclass(frozen=True) class WorkerResult`: `persona: str`, `ranked: tuple[str, ...]` (real names, after unmasking), `claims: Mapping[str, tuple[Claim, ...]]`, `dropped: DropReason | None`, `raw: str | None`, `cache_hit: bool`, `wall_ms: float`; `valid` property = `dropped is None`.
- `run_worker(persona, digest: Digest | None, alias: AliasMap, gateway: LLMGateway) -> WorkerResult` — never raises for model errors. (Task 9 adds `cache: ResponseCache | None = None`.)

- [ ] **Step 1: tests** (fake gateway returning fixed text): `test_valid_answer_unmasked`; `test_claim_citing_missing_id_dropped`; Review Focus 4 (`test_real_name_unknown_alias_or_foreign_id_invalid`); `test_more_than_five_truncated_to_five`; `test_duplicate_service_keeps_first`; `test_schema_failure_retries_once_then_drops`; `test_timeout_is_a_drop_not_an_exception`; `test_no_digest_drops_without_calling`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 8: Merge, μ, σ

**Files:** Create `helios/pipelines/l_pipe/merge.py`; Test `tests/pipelines/l_pipe/test_merge.py`.

**Interfaces — Produces:** `@dataclass(frozen=True) class MergeResult`: `scores: dict[str, float]`, `ranked: tuple[str, ...]`, `mu: float | None`, `sigma: float | None`, `k: int`; `merge(results: Sequence[WorkerResult]) -> MergeResult` (invalid results ignored; scores rounded to `MU_DIGITS`).

- [ ] **Step 1: tests** (exact):
  - `test_two_agreeing_workers`: A = [a, b, c], B = [a, c] → scores a 1, b 0.4, c 0.7; ranked a, c, b; μ = round(1/2.1, 6); gap 0.3, agreement 1 → σ = 0.7.
  - `test_two_disagreeing_workers`: A = [a, b], B = [b, a] → a 0.9, b 0.9; tie → a first; agreement 0 → σ = 1.
  - `test_single_worker_sigma_is_one`: k = 1, any list → σ = 1.
  - `test_three_workers_two_agree`: A = [a], B = [a], C = [b] → agreement (2 − 1)/(3 − 1); σ = 1 − agreement × gap with gap from the merged scores.
  - `test_no_valid_worker`: k = 0 → empty, μ and σ None.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 9: Model digest and response cache

**Files:** Create `helios/pipelines/l_pipe/cache.py`; Modify `workers.py` (the `cache` parameter), `ollama_client.py` (add `model_digest(timeout_s: float) -> str` from `/api/show` or `/api/tags`), `gateway.py` (add `replay(result: OllamaGenerateResult) -> None`, counted like a real call); `.gitignore` (cache file); Test `tests/pipelines/l_pipe/test_cache.py`.

**Interfaces — Produces:** `class ResponseCache(path: Path)`: `get(key: str) -> CachedCall | None`, `put(key: str, call: CachedCall) -> None`; `CachedCall` = text, prompt_tokens, completion_tokens, compute_ms, wall_ms; `cache_key(model_digest: str, prompt_sha: str, rendered: str) -> str`. `run_worker` (Task 7) uses it: hit → `gateway.replay`, `cache_hit` True, `wall_ms` = stored.

- [ ] **Step 1: tests:** `test_hit_replays_usage_and_wall_time`; `test_key_changes_with_model_digest_prompt_sha_or_input`; `test_miss_calls_model_and_stores`; `test_failed_call_not_cached`; `test_model_digest_parsed` (mocked HTTP).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 10: `run_lpipe` on workers

**Files:** Modify `helios/pipelines/l_pipe/pipeline.py`; Test `tests/pipelines/l_pipe/test_pipeline.py` (update existing L-pipe tests that assume `rca_v1`).

**Interfaces — Produces:** `run_lpipe(incident_id, snapshot_hash, evaluation_phase, run_id, *, window: TelemetryWindow, trigger: TriggerRecord, root: Path, client: OllamaClient | None = None, cache: ResponseCache | None = None, confirmatory: bool = False) -> dict[str, Any]` — candidates (Global Constraints) → alias map → three personas in order, sequentially → merge → verdict dict as today plus `evidence` (digests' lines, each worker's raw answer, drop reason, cache hit, merged scores) and `cache_hit` (all calls hit). Status RANKED / ABSTAINED (k = 0) / FAILED (exception outside workers, e.g. digest build). `confirmatory=True` with provisional prompt SHAs → raises before any call. Records the model digest and prompt SHAs in `prompt_version`.

- [ ] **Step 1: tests** (fake client): `test_ranked_verdict_with_mu_sigma`; Review Focus 5 (`test_all_workers_invalid_abstains_with_reasons`); `test_rcaeval_window_runs_two_workers`; `test_digest_crash_is_failed`; `test_confirmatory_refuses_provisional_prompts`; `test_calls_are_sequential` (fake client asserts no overlap); `test_never_reads_dpipe_or_gpipe` (static: module imports nothing from `d_pipe`, `g_pipe`, `graph.ueg_c_builder`).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 11: Runner wiring, evidence, leakage test, rerun equality

**Files:** Modify `helios/orchestrator/runner.py` (pass `window`, `trigger`, `root`, cache, confirmatory flag; store `evidence` via `insert_evidence` for `lpipe`), `tests/evaluation/test_no_ground_truth_leak.py`; Test `tests/orchestrator/test_runner_lpipe.py`.

- [ ] **Step 1: tests:** `test_runner_stores_lpipe_evidence`; `test_llm_only_variant_runs_lpipe_without_graph` (HELIOS-LLM-only manifest, fake client); leak test extended: an orchestrator run over a build window with a recording fake client — no prompt contains the incident ID, a data path, a fault name of the corpus, the injection time, or a real service/component name; no ground-truth file opened (existing trap); `test_rerun_bitwise_equal` (same window twice, cache off, fake deterministic client → equal decision hash).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 12: Build-run tool

**Files:** Create `helios/evaluation/lpipe_calibration.py`, `bin/lpipe_build_run.py`; Test `tests/evaluation/test_lpipe_calibration.py`, `tests/test_lpipe_build_run_cli.py`.

**Interfaces — Produces:**
- `split_of(incident_id: str) -> Literal["dev", "heldout"]` — first byte of SHA-256(incident_id) even → dev.
- `load_lpipe_cases(*, root: Path, key: bytes) -> list[LPipeCase]` — `otel_build_v3` + `rcaeval_build` via `trigger_calibration.load_cases`.
- `bin/lpipe_build_run.py [--round N] [--split dev|heldout|both]`: refuses the pool; frozen trigger per case; `run_lpipe` with the real client and cache; writes `docs/sprints/s2-reasoning/calibration/lpipe_round<N>.json` — aggregates only: HR@3 of L-pipe and of each worker alone per corpus × split, k histogram, drop reasons, mean seconds per incident, cache hits, prompt SHAs and model digest. No incident IDs.

- [ ] **Step 1: tests:** `test_split_is_stable_and_roughly_even` (all build IDs: both parts within 40–60 %); `test_cases_count_558`; `test_tool_refuses_the_pool`; `test_report_has_no_incident_ids` (tiny fake run).
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 13: Rules entry; close PR 1

- [ ] **Step 1:** Draft the pre-work deviation entry in `.superpowers/sdd/s2_3_implementation_plan/deviation_drafts.md` — clause: S2.3 design §2, §5, D11, Ch3 Table 18 A-H2; change: L-a…L-i, digest rules and caps, alias rules, merge and σ, revision budget (≤ 3 rounds, judged on dev), dev/held-out split, cache; reason: owner decisions 2026-10-30; consequence: confirmatory L-pipe on the pool uses metrics and logs only (k ≤ 2); prompts frozen in PR 2 under these rules only. **Owner signs**; CLI append → `verify` → `verify-public` → `bin/verify_ledgers.py` → `tests/test_deviation_log.py`; mirror row; commit. **No worker sees a build case before this entry is signed.**
- [ ] **Step 2:** Full pre-push gate; fresh whole-branch review on the most capable model; Critical/Important fixed test-first; minors to the ledger; push; open PR 1. Row stays IN_PROGRESS.

## PR 2 — build runs, prompt freeze, freeze entry

### Task 14: Build runs and revisions

- [ ] **Step 1:** Round 1: `bin/lpipe_build_run.py --round 1 --split both`; commit the report. Revise prompts only from the dev numbers and dev examples; at most rounds 2 and 3, each committed with its report and a one-line reason in design §10. Held-out numbers are read but never drive a revision.
- [ ] **Step 2:** Rerun one round's dev set with the cache off on 10 cases → equal verdicts (determinism on the real model). **Bring the last round to the owner before freezing.**

### Task 15: Freeze

- [ ] **Step 1 (after owner OK):** Test `test_frozen_prompt_shas_match_files_and_report` (the three SHAs in `lpipe_config.WORKER_PROMPT_SHAS` = the files = the last report; `EXPECTED_MODEL_DIGEST` = the report's). FAIL → set the constants → PASS; `rca_v1` no longer used (file kept, marked superseded); full suite; commit.
- [ ] **Step 2:** Design §10: rounds table (HR@3 per corpus × split, per worker, k histogram, seconds per incident), validity notes (residual operation-word cue; RCAEval 375 metric-only cases; OTel-to-pool shift T21). Register update.
- [ ] **Step 3:** Freeze deviation entry drafted → owner signs → CLI → verify → mirror; close `S2-M7-ENG03` DONE in its own commit; full gate; fresh review; PR 2.
