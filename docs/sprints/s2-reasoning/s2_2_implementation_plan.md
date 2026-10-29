# S2.2 G-pipe culprit-versus-victim ranker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** G-pipe ranks the culprit above its victims using three trace-graph features (leads, self/wait time, ghost edges), chosen among three candidate rankers by a rule fixed before the run, with σ and per-suspect evidence.

**Architecture:** Span-level features in `helios/graph/span_features.py`; per-service feature table and the three candidates in `helios/pipelines/g_pipe/`; frozen choice in `data/frozen/gpipe_params.json` loaded by the runner; selection in `helios/evaluation/gpipe_calibration.py` + `bin/gpipe_select.py`. PR 1 builds everything and records the rule (provisional parameters = plain PPR); PR 2 runs the selection and freezes.

**Tech Stack:** Python 3.11, pandas, numpy, scipy (optimize), networkx, pydantic v2, duckdb; pytest.

**Spec:** `docs/sprints/s2-reasoning/s2_2_gpipe_design.md` (approved 2026-10-29). Tracking row **S2-M7-ENG02**.

## Global Constraints

- No service identity in features or model (F3): no names, one-hot or per-service constants; a feature-audit test fails training if one appears.
- No injection time, fault or label on the run path; labels only score build runs. Pool refused by every tool before tag `build-freeze`; tool output is counts and aggregates only.
- Build data: `otel_build_v3` (63) + `data/captures` minus `imageSlowLoad` (16) = **79 cases, 9 fault types**.
- Trigger and D-pipe from `data/frozen/trigger_detector.json` and `data/frozen/dpipe_params.json`; never re-tuned here.
- No feature reads window start/end or the trigger's position in the window.
- Wait = **union of child-span intervals in other services**, never the sum (G-d). Ghost-edge baseline = spans before `t` (G-e).
- Feature-weighted PPR constants fixed in code before the run: edge weight = caller's wait share after `t`, self-loop = self share, restart ×2 for a leader, α = `GPIPE_PPR_ALPHA` (0.85).
- Selection: ≥ 3 more top-3 hits of 79 **and** better on more held-out faults than worse, else the simpler candidate; learned vs feature-weighted, then survivor vs plain PPR.
- `ueg_structural` OFF → plain PPR on the flattened graph (G-h).
- σ = 1 − gap × strength, in [0, 1] (design §5.4).
- Routing gate (`DISAGREEMENT_THRESHOLD`) unchanged in the runner; selection ignores it and reports the gated view.
- Every new module references the VCL (flag-guard); G-pipe stays under `VCLFlag.GPIPE`; no new VCL flag; never edit `helios/vcl/variants.py`, `research/osf/*`, `docs/tracking/metric_contract.md`, the seed register.
- Deviation entries via the CLI only, signed after owner review; tracking rows IN_PROGRESS → DONE in separate commits; never `cd` into subdirectories; full gate before each PR; the owner merges.

## Review Focus

1. A span whose parent is missing from the capture (truncated trace) → treated as a root: no edge, no wait for anyone, no crash. *(Task 3 test)*
2. Child spans in the **same** service (internal operations) → neither wait nor a call edge. *(Task 3 test)*
3. A child interval extending past its parent (clock skew) → clipped to the parent interval, so self time never goes below zero. *(Task 3 test)*
4. A service with no spans after `t` (calls stopped, e.g. paymentUnreachable) → features defined (zero calls, wait share zero), no NaN in the score. *(Task 4 test)*
5. RCAEval-format P2 (adapter output, microsecond columns, empty `parent_span_id` as `""`) → same features as OTel; `""` and `None` both mean "no parent". *(Task 3 test)*

---

## PR 1 — features, candidates, selection tool, rule entry

### Task 1: Open the row

- [ ] **Step 1:** Branch `s2/gpipe` from `main`, carrying the two design commits of `s2/gpipe-design`. Set `S2-M7-ENG02` to IN_PROGRESS (Started 2026-10-29) in `docs/tracking/helios_mvp_tracking.md`, mutable columns only.
- [ ] **Step 2:** `poetry run python scripts/validate_tracking.py` → exit 0. Commit `tracking: S2-M7-ENG02 IN_PROGRESS (S2.2 G-pipe)`.

### Task 2: K-hop re-check on the OTel build cases (carry-over; before any selection)

**Files:** Modify `bin/khop_calibrate.py`; Test `tests/test_khop_calibrate_cli.py` (create if absent).

**Interfaces — Produces:** `--corpus` choices `build`, `captures`, `otel_build_v3`.

- [ ] **Step 1:** Test `test_otel_build_v3_corpus_reads_its_signed_labels`: `_cases("otel_build_v3", None)` returns `data/otel/build_v3`, 63 IDs in `build_v3_manifest.json` order, labels from the signed `ground_truth_build_v3.json` (`verify_ground_truth` with the ledger key). Run → FAIL.
- [ ] **Step 2:** Implement the third branch of `_cases`. Run → PASS.
- [ ] **Step 3:** Run `bin/khop_calibrate.py --corpus otel_build_v3` and `--corpus captures`. Expected: K = 3, top-n 50 keeps the root in every case (S1 exit: 63/63 on v1). If any root is lost, or the tool's rule would pick another K or top-n: **stop and report to the owner** (a change of K is its own deviation entry).
- [ ] **Step 4:** Results table into design note §10 (new section). Commit.

### Task 3: Span features (interval union, call edges, ghost edges)

**Files:** Create `helios/graph/span_features.py`; Test `tests/graph/test_span_features.py`.

**Interfaces — Produces** (P2 columns as written by `helios/adapters/rcaeval.py` and the OTel capture):
- `split_at(spans: pd.DataFrame, t_s: float) -> tuple[pd.DataFrame, pd.DataFrame]` — by span start (`start_time_us`).
- `call_edges(spans) -> frozenset[tuple[str, str]]` — (parent service, child service) for parent–child pairs in different services.
- `wait_by_callee(spans) -> dict[tuple[str, str], float]` — per (caller, callee): summed over the caller's spans, the **union length** of that callee's child intervals clipped to the parent interval (µs).
- `span_totals(spans) -> dict[str, tuple[float, float]]` — per service: (total duration µs, total self µs); self = duration − union of all cross-service child intervals (clipped).
- `ghost_edges(before, after) -> frozenset[tuple[str, str]]` = `call_edges(after) - call_edges(before)`.

- [ ] **Step 1: tests** (exact numbers on hand-built frames, times in µs):
  - `test_concurrent_children_count_once`: parent 0–120; children in B 10–60 and in C 40–90 → wait on B 50, wait on C 50, total wait 80, self 40.
  - `test_overlapping_children_of_one_callee_union`: two B children 10–60 and 40–90 → wait on B 80.
  - `test_same_service_child_is_not_wait_or_edge` (Review Focus 2).
  - `test_child_past_parent_is_clipped` (RF 3): parent 0–120, child 80–150 → wait 40, self 80.
  - `test_missing_parent_is_a_root` (RF 1).
  - `test_empty_parent_string_and_none_both_mean_root` (RF 5).
  - `test_edge_only_before_is_not_ghost`; `test_edge_only_after_is_ghost`.
- [ ] **Step 2:** Run → FAIL (module missing).
- [ ] **Step 3:** Implement. Interval union: sort children by start per parent, merge overlaps; vectorise with groupby where possible (a v3 window holds about 40k spans).
- [ ] **Step 4:** Run → PASS; ruff, black, mypy. Commit `feat(s2.2): span features — call edges, wait by interval union, ghost edges`.

### Task 4: Per-service feature table, leads, feature audit

**Files:** Create `helios/pipelines/g_pipe/features.py`; Test `tests/pipelines/g_pipe/test_features.py`.

**Interfaces:**
- Consumes: Task 3; `service_scores(window, bucket_s, root=...)`, `ServiceScores`, `DetectorParams`, `robust_scale` (`helios/telemetry/trigger.py`); `TriggerRecord.trigger_time_s`.
- Produces:
  - `FEATURE_COLUMNS: tuple[str, ...]` = `("dpipe_score", "ppr_score", "in_degree", "out_degree", "callers_led", "callees_leading", "self_shift", "wait_pooled", "wait_pooled_rise", "ghost_in", "ghost_out", "error_share_shift")`.
  - `@dataclass(frozen=True) class GraphFeatures`: `services: tuple[str, ...]`; `table: np.ndarray` (rows = services, columns = `FEATURE_COLUMNS`); `edge_wait_after: dict[tuple[str, str], float]` (wait share); `self_share: dict[str, float]`; `leaders: frozenset[str]`; `ghosts: frozenset[tuple[str, str]]`; `onset_bucket: dict[str, int]`.
  - `compute_features(window, trigger, dpipe_scores: dict[str, float], ppr_scores: dict[str, float], services: Sequence[str], detector: DetectorParams, *, root: Path | None = None) -> GraphFeatures | None` — `None` when the window has no traces or no spans on one side of `t`.
  - `onsets(scores: ServiceScores, trigger_time_s: float, detector: DetectorParams) -> dict[str, int]` — first bucket **at or after the trigger bucket** whose score reaches `detector.threshold`.
  - `assert_no_identity(columns: Sequence[str], services: Sequence[str]) -> None` — `ValueError` if a column is not in `FEATURE_COLUMNS` or contains a service name or stem (`service_key`).
- Definitions: `wait_pooled` = sum over callers of their after-`t` wait share on the service; `wait_pooled_rise` = that minus the before-`t` value; `self_shift` = (median self share after − before) ÷ `robust_scale` of before (gauge rule); `error_share_shift` = error-span share after − before; leads per design §5.1.

- [ ] **Step 1: tests:** `test_onset_ignores_crossings_before_the_trigger`; `test_callee_with_onset_leads_caller_without_one`; `test_leads_need_a_full_bucket` (same bucket → no lead); `test_service_without_spans_after_t_has_finite_features` (RF 4); `test_no_split_gives_none`; `test_feature_audit_rejects_a_service_named_column`; `test_feature_columns_carry_no_service_names` (against the service names of a v3 graph fixture); `test_features_ignore_window_bounds` (same spans and trigger, window start and end moved → identical table).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** PASS, lint, types. Commit.

### Task 5: The three candidate rankers

**Files:** Create `helios/pipelines/g_pipe/rankers.py`; Modify `helios/pipelines/g_pipe/pipeline.py` (`_ppr_traverse` → `plain_ppr`, same behaviour); Test `tests/pipelines/g_pipe/test_rankers.py`.

**Interfaces — Produces:**
- `plain_ppr(snapshot: UEGCSnapshot, seeds: dict[str, float]) -> dict[str, float]` — today's traversal scores, candidates only.
- `LEADER_RESTART_FACTOR: int = 2`; `weighted_ppr(features: GraphFeatures, seeds: dict[str, float]) -> dict[str, float]` — design §5.2.
- `RIDGE_LAMBDA: float = 1` (fixed before the run).
- `@dataclass(frozen=True) class LinearRanker`: `weights`, `mean`, `scale` (tuples of float, `FEATURE_COLUMNS` order); `@classmethod fit(cls, examples: Sequence[tuple[GraphFeatures, str, bool]]) -> LinearRanker` (each example: features, root label, stem flag; pairwise logistic loss of the root against every other service in its window; L2 = `RIDGE_LAMBDA`; standardise columns; `scipy.optimize.minimize(method="L-BFGS-B")` from zeros); `score(self, features: GraphFeatures) -> dict[str, float]`.

- [ ] **Step 1: tests:** `test_plain_ppr_matches_the_previous_traversal` (fixture graph, expected dict recorded from the current code before the move); `test_weighted_ppr_moves_mass_from_victim_to_culprit` (A waits 95% on B, seeds favour A → B above A); `test_weighted_ppr_leader_restart_doubles`; `test_linear_ranker_fit_is_deterministic` (two fits → identical weights); `test_linear_ranker_learns_a_planted_feature` (root always highest `wait_pooled` → that weight largest); `test_linear_ranker_refuses_identity_columns`.
- [ ] **Step 2–4:** FAIL → implement → PASS; existing G-pipe and runner tests still pass. Commit.

### Task 6: Frozen parameters, `run_gpipe`, σ, evidence, noStructural

**Files:** Create `helios/pipelines/g_pipe/params.py`, `data/frozen/gpipe_params.json`; Modify `helios/pipelines/g_pipe/pipeline.py`; Test `tests/pipelines/g_pipe/test_pipeline_s22.py`.

**Interfaces:**
- `data/frozen/gpipe_params.json` (PR 1, provisional): `{"ranker": "ppr", "weights": null, "mean": null, "scale": null, "provisional": true}`.
- `GPipeParams` (frozen dataclass: `ranker: Literal["ppr", "weighted_ppr", "learned"]`, `model: LinearRanker | None`, `provisional: bool`); `GPIPE_PARAMS_PATH`; `load_gpipe_params(path=GPIPE_PARAMS_PATH) -> GPipeParams` (missing file or key → error, as D-pipe); `gpipe_params_hash(params) -> str` (sha256 of `canonical_json`).
- `run_gpipe(..., window: TelemetryWindow | None = None, trigger: TriggerRecord | None = None, params: GPipeParams | None = None, detector: DetectorParams | None = None)` — new keyword arguments. Plain PPR when `params` is None, `ranker == "ppr"`, `not manifest.ueg_structural` (G-h) or `compute_features(...)` is None. Output adds `"sigma"` and `"evidence"`.
- `gpipe_sigma(scores: dict[str, float], features: GraphFeatures | None, top: str) -> float | None` — design §5.4; None without features.
- `evidence_for(features: GraphFeatures, ranked: Sequence[str], k: int = 3) -> dict[str, Any]` — per top-k suspect: `wait_from` {caller: share}, `leads` [callers], `ghost_edges` [[a, b]], `self_shift`; floats rounded by `canonical_json`.

- [ ] **Step 1: tests:** `test_no_structural_uses_plain_ppr` (`get_variant("HELIOS-noStructural")`, params `weighted_ppr` → ranking equals `plain_ppr`); `test_no_split_falls_back_to_plain_ppr`; `test_sigma_in_unit_interval_and_lower_with_more_evidence`; `test_evidence_has_no_label_or_time_keys`; `test_params_file_missing_key_is_an_error`; `test_params_hash_covers_every_field`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 7: Runner wiring, evidence storage, cross-process equality

**Files:** Modify `helios/orchestrator/runner.py`, `helios/store/result_store.py`, `bin/trigger_check.py`; Test `tests/test_orchestrator_runner.py`, `tests/test_trigger_check_cli.py`, the result-store tests.

**Interfaces:**
- `RunOrchestrator(..., gpipe_params: GPipeParams | None = None)` → default `load_gpipe_params()`; confirmatory runs refuse `provisional` (extend the existing detector/D-pipe refusal).
- The runner passes `window`, `trigger`, `params` and the frozen detector to `run_gpipe`.
- `ResultStore.insert_evidence(run_id: str, incident_id: str, pipeline: str, evidence: dict[str, Any]) -> None` — new table `evidence_row(run_id, incident_id, pipeline, evidence_json)`; `fetch_evidence(run_id: str, pipeline: str) -> dict[str, Any] | None`.
- `bin/trigger_check.py --with-gpipe`: prints each window's G-pipe verdict and evidence (needs a graph; ignores the gate, as the selection does).

- [ ] **Step 1: tests:** `test_confirmatory_run_refuses_provisional_gpipe_params`; `test_gpipe_evidence_is_stored_with_the_run`; `test_gpipe_verdict_identical_across_processes` (subprocess twice with `--with-gpipe` on a synthetic window with traces, explicit `--params`); store round-trip. The S1.9 leakage scan (existing test or tool) passes with the new G-pipe modules on the run path.
- [ ] **Step 2–4:** FAIL → implement → PASS; full suite. Commit.

### Task 8: Selection logic and tool

**Files:** Create `helios/evaluation/gpipe_calibration.py`, `bin/gpipe_select.py`; Test `tests/evaluation/test_gpipe_calibration.py`, `tests/test_gpipe_select_cli.py`.

**Interfaces — Produces:**
- `MARGIN_HITS: int = 3`; `CANDIDATES = ("learned", "weighted_ppr", "ppr")` (most to least complex).
- `@dataclass(frozen=True) class GPipeCase`: `incident_id`, `window`, `root_cause`, `fault`, `stem: bool`.
- `load_gpipe_cases(*, root: Path, key: bytes) -> list[GPipeCase]` — `otel_build_v3` via `trigger_calibration.load_cases` (stem False) plus `data/captures` with `data/ground_truth.json` (`fault_type`; stem True), excluding `fault_type == "imageSlowLoad"`; nothing else.
- `beats(complex_hits: Mapping[str, list[int]], simple_hits: Mapping[str, list[int]]) -> bool` — per-fault lists of hits; True iff the total difference ≥ `MARGIN_HITS` and the number of faults better > the number worse.
- `select_gpipe(hits: Mapping[str, Mapping[str, list[int]]]) -> str` — learned vs weighted_ppr, then the survivor vs ppr; ties to the simpler.
- `bin/gpipe_select.py`: refuses a provisional detector or D-pipe and the pool. Per case: frozen trigger, `incident_graph` (HELIOS-Full), D-pipe verdict, plain PPR, features; learned ranker scored by leave-one-fault-out (9 folds). Writes `docs/sprints/s2-reasoning/s2_2_gpipe_selection.json` (aggregates: per candidate and fault HR@3, totals, D-pipe HR@3 on the same cases, fallback count, gated-view count and HR@3, selected candidate, the learned ranker refit on all 79 with its hash, detector and D-pipe hashes, and the frozen trigger's outcome per corpus — threshold vs fallback — since the earlier captures were not in the S2.1 calibration) and prints counts. Never writes `data/frozen/`.

- [ ] **Step 1: tests:** `test_learned_needs_three_more_hits` (two more → simpler); `test_learned_needs_more_faults_better_than_worse` (three more, all from one fault, worse on two → simpler); `test_tie_goes_to_the_simpler`; `test_survivor_then_faces_plain_ppr`; `test_cases_exclude_image_slow_load_and_count_79` (real build data); `test_tool_refuses_the_pool`; `test_tool_refuses_a_provisional_detector`.
- [ ] **Step 2–4:** FAIL → implement → PASS. Commit.

### Task 9: Rule entry; close PR 1

- [ ] **Step 1:** Draft the pre-run deviation entry in `.superpowers/sdd/s2_2_implementation_plan/deviation_drafts.md` — clause: S2.2 design §5, D11, Ch3 Table 18 A-H8; change: features §5.1, candidates and constants §5.2, rule §5.3, σ §5.4, build data (G-f, imageSlowLoad excluded), noStructural (G-h), K-hop re-check result; reason: owner decisions G-a…G-h; consequence: what A-H8 measures; G-pipe frozen in PR 2 by this rule only. **Owner signs**; then CLI append, `verify`, `verify-public`, `bin/verify_ledgers.py`, `tests/test_deviation_log.py`; mirror row; commit.
- [ ] **Step 2:** Full pre-push gate (root `CLAUDE.md`); fresh whole-branch review on the most capable model; Critical/Important fixed test-first; minors to the ledger; push; open PR 1. The row stays IN_PROGRESS.

## PR 2 — run, freeze, result entry

### Task 10: Selection run and freeze

- [ ] **Step 1:** Run `bin/gpipe_select.py`; copy the report to `docs/sprints/s2-reasoning/calibration/gpipe_run1.json`; commit as evidence. **Bring the result to the owner before freezing.**
- [ ] **Step 2 (after owner OK):** Test `test_frozen_gpipe_params_are_the_selection` (frozen file = the report's selected candidate and hash; `provisional` false; the report's detector and D-pipe hashes = the frozen ones). FAIL → write `data/frozen/gpipe_params.json` → PASS; full suite; commit.
- [ ] **Step 3:** `bin/trigger_check.py --corpus otel_build_v3 --with-gpipe` twice → equal digests. Design note §10: per-candidate HR@3, D-pipe lift, gated view, fallbacks, frozen hash. Validity: T19 note (earlier captures' mid-window onset; no feature reads position); a new or extended threat for the OTel-to-pool shift. Register update.
- [ ] **Step 4:** Result deviation entry drafted → owner signs → CLI → verify → mirror; close `S2-M7-ENG02` DONE in its own commit; full gate; fresh review; PR 2.
