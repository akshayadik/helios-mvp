# S2.9 Rating Rubric and Blind Labelling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Everything two external raters and an adjudicator need to label HELIOS-Full and HELIOS-noLLM narratives blind, built and tested on fixtures and build data, so rater training (κ ≥ 0.7) can start as soon as rater 2 is confirmed.

**Architecture:** A new evaluation package `helios/labelling/` turns signed CoE entries (S2.7, step N from S2.8) into a masked, shuffled labelling set with code-generated planted claims and a sealed key; a standard-library HTTP server bound to the loopback interface serves one claim at a time per person and appends every label to its own HMAC-chained, Ed25519-anchored annotations ledger; `helios/evaluation/rater_agreement.py` computes κ, the adjudicated consensus and H_fact. A build-data run keeps signed ledgers from which the training and onboarding sets are drawn.

**Tech Stack:** Python 3.11 standard library (`http.server`, `hmac`, `secrets`, seeded `random.Random`), existing `helios.vcl.hmac_chain`, `helios.vcl.ed25519`, `helios.narrative` (Claim, verifier), plain HTML + JavaScript page. No new dependencies.

**Spec:** `docs/sprints/s2-reasoning/s2_9_rubric_design.md` (approved 2026-11-01, R-a to R-o).

## Global Constraints

- Row S2-M7-RES01 stays IN_PROGRESS through this plan; DONE needs κ ≥ 0.7 with real raters (owner item, after rater 2 is confirmed, due 30 Nov).
- No ground-truth file is ever opened by any tool in this plan (entry 65); a test proves it per tool.
- Pool lock (D11): confirmatory-phase CoE entries are refused unless git tag `build-freeze` exists; pool output is counts only.
- The seed register (`helios/research/seeds.py`, `research/osf/seeds.json`) is not touched: the shuffle seed is derived (R-o).
- Annotations ledger: own Ed25519 key pair (R-n); env var `ANNOTATIONS_ED25519_PRIVATE_KEY`, public key `keys/annotations_ed25519.pub.pem`; the deviation-log key is never loaded by the server. Generating the real key is an owner action; tests use throwaway keys.
- Server binds the loopback interface only; the browser never receives `key.json`, arms, run or case IDs, planted flags, or other people's labels (the adjudicator sees two unattributed labels only).
- Error categories, in this order (R-e): `numeric_drift`, `entity_mismatch`, `directional_inversion`, `log_quote_mismatch`, `missing_citation`.
- Planted shares of all shown items: training about a quarter, confirmatory about one in ten (in code: `TRAINING_PLANTED_SHARE = 1 / 4`, `CONFIRMATORY_PLANTED_SHARE = 1 / 10`). Detection floor `DETECTION_FLOOR = 4 / 5` per sitting.
- Header shown to raters: top-3 suspects only, no confidence or state (R-k).
- Every new module outside `helios/vcl/` imports `VCLFlag` (flag-guard); scratch scripts carry a `# HELIOS_ENABLE_*` comment. The research-compliance hook blocks four float and integer literals in any Write/Edit; express them as fractions or prose.
- Tracking: every commit stays valid under `scripts/validate_tracking.py --range main..HEAD`; local `--no-ff` merge on owner go-ahead; never push.

## Review Focus

1. **Concurrent use:** two raters at once, or one rater in two tabs, must never double-label or skip an item, and a label for an item not currently served to that person is refused (Task 6, `test_label_for_unserved_item_is_refused`, `test_two_tabs_get_the_same_next_item`).
2. **Server restart mid-sitting:** state is rebuilt from the ledger (latest label per item and person); a truncated or edited ledger refuses to start (Task 6, `test_restart_resumes_from_ledger`, `test_tampered_ledger_refuses_to_start`).
3. **Missing evidence looks the same everywhere:** a real claim whose cited ID is absent and a planted missing-citation claim render the identical "evidence not found" card (Task 2 `test_missing_evidence_card`, Task 3 `test_planted_and_real_items_have_the_same_shape`).
4. **Planted items indistinguishable in `set.json`:** same keys, same ID format, no ordering tell (Task 4, `test_set_items_have_one_shape_and_planted_are_spread`).
5. **Odd entries:** an entry with no step N (noExpl), no ranked suspects, or empty slots is skipped and counted, never a crash (Task 4, `test_odd_entries_are_skipped_and_counted`).

---

## PR 1 — instrument (branch `s2/rubric`)

### Task 1: Annotations ledger and its key

**Files:**
- Create: `helios/labelling/__init__.py`, `helios/labelling/annotations.py`
- Modify: `bin/verify_ledgers.py` (add `--annotations DIR [--public-only]`), `.gitignore` (add `data/labelling/`)
- Test: `tests/labelling/test_annotations.py`, `tests/test_verify_ledgers_annotations.py`

**Interfaces:**
- Produces: `class AnnotationLedger(HMACChainedLog)` with `LOG_KIND = "annotations"`, `ANCHOR_ED25519 = True`, `REQUIRED_FIELDS = ("set_hash", "item", "person", "kind", "verdict", "category", "note", "dwell_ms")`; `kind` ∈ `{"label", "adjudication", "blind_guess"}`; `verdict` ∈ `{"supported", "unsupported"}` for labels and adjudications, `{"A", "B", "unsure"}` for blind guesses. `def latest(ledger: AnnotationLedger, kind: str) -> dict[tuple[str, str], dict]` (key = (item, person)). Constants `ANNOTATIONS_ENV_VAR` (holding the environment variable name given in Global Constraints, named like `ED25519_ENV_VAR` in `bin/log_deviation.py` so gitleaks does not flag it) and `ANNOTATIONS_PUBLIC_KEY_FILE = Path("keys/annotations_ed25519.pub.pem")`. `def verify_annotations_dir(directory: Path, key: bytes | None, public_path: Path) -> int` in `bin/verify_ledgers.py`.

- [ ] **Step 1: Failing tests**: `test_append_and_latest_wins` (two labels by R1 on item x → `latest` gives the second); `test_tamper_edit_remove_truncate_fail_verify` (each fails `verify()` and `verify_public`); `test_unsigned_anchor_refused_when_key_given` (monotonic signing as CoE); `test_bad_kind_or_category_refused` (`ValueError` before append; category required iff verdict is unsupported); `test_verify_ledgers_annotations_cli` (exit 0 on a clean dir, non-zero on an edited file, `--public-only` works without the HMAC secret).
- [ ] **Step 2: Run** `poetry run pytest tests/labelling/test_annotations.py tests/test_verify_ledgers_annotations.py -q --no-cov` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** by subclassing as `CoELedger` does; CLI mirrors `verify_coe_dir` with glob `*.annotations.jsonl`.
- [ ] **Step 4: Run** the same command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(s2.9): annotations ledger (own Ed25519 anchor key) and verify_ledgers --annotations`.

### Task 2: Claims and evidence cards from a CoE entry

**Files:**
- Create: `helios/labelling/cards.py`
- Test: `tests/labelling/test_cards.py`

**Interfaces:**
- Consumes: CoE entry dicts (S2.7 shape), step N (`slots[name]["claims"]` as `Claim.model_dump`), `helios.narrative.claims.Claim`.
- Produces: `@dataclass(frozen=True) class Card: id: str; service: str | None; text: str; values: dict[str, Any]` (only `before`, `after`, `unit`, `value` present on the item; for `L:log:` items the text is the logged template only); `MISSING_CARD_TEXT = "evidence not found"`; `def header_top3(entry) -> str` (`"Top suspects: 1. a, 2. b, 3. c"`); `def displayed_claims(entry) -> list[tuple[str, int, Claim]]` (slot, index, claim) in display order, `[]` without step N; `def cards_for(claim: Claim, entry) -> list[Card]` (one per cite; `F` rendered as the fused top 3).

- [ ] **Step 1: Failing tests** on `tests.narrative.test_verifier.ENTRY` with a step N built from `template_slots`: `test_header_has_no_confidence_or_state` (no `0.91`, no `confirmed`); `test_displayed_claims_follow_display_order`; `test_cards_resolve_each_cite` (`D:cart:latency` card has before 120, after 900, unit `ms`); `test_log_card_shows_only_template_text` (no "lines before trigger"); `test_missing_evidence_card` (cite `D:nope:latency` → one card with `MISSING_CARD_TEXT`, id kept); `test_no_step_n_gives_no_claims`.
- [ ] **Step 2: Run** `poetry run pytest tests/labelling/test_cards.py -q --no-cov` — FAIL.
- [ ] **Step 3: Implement**; reuse `helios.narrative.verifier.log_template_text`.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(s2.9): claim and evidence cards from CoE entries (top-3 header, template-only log cards)`.

### Task 3: Planted claims

**Files:**
- Create: `helios/labelling/planted.py`
- Test: `tests/labelling/test_planted.py`

**Interfaces:**
- Consumes: `Claim`, `helios.narrative.verifier.verify` and `Reason`, `NarratorParams`.
- Produces: `CATEGORIES: tuple[str, ...]` (the Global Constraints order); `EXPECTED_REASON: dict[str, set[Reason]]` = numeric_drift → {NUMBER_NOT_IN_EVIDENCE}, entity_mismatch → {FOREIGN_SERVICE, WRONG_EDGE, KIND_MISMATCH}, directional_inversion → {WRONG_DIRECTION}, log_quote_mismatch → {SNIPPET_NOT_FOUND}, missing_citation → {UNKNOWN_ID}; `def corrupt(claim: Claim, entry, category: str, rng: random.Random, params) -> Claim | None` (None when the category cannot apply); `def plant(sources: list[tuple[str, Claim, Mapping]], share: float, rng: random.Random, params) -> list[tuple[str, Claim, str]]` returning (source key, planted claim, category), categories balanced round-robin over those that apply, `share` = planted ÷ (real + planted).

- [ ] **Step 1: Failing tests**: `test_each_category_is_rejected_by_the_verifier_with_its_reason` (every category on every claim kind it applies to on ENTRY → `verify(...)` in `EXPECTED_REASON[category]`); `test_corruptions_keep_the_sentence_shape` (same kind, one line, word count within two of the source); `test_numbers_move_beyond_tolerance_and_keep_their_unit`; `test_plant_share_and_balance` (240 sources at share one quarter → 80 planted, every applicable category present); `test_plant_is_deterministic_for_a_seed`; `test_planted_and_real_items_have_the_same_shape` (`model_dump` keys equal for a real and a planted claim of one kind).
- [ ] **Step 2: Run** `poetry run pytest tests/labelling/test_planted.py -q --no-cov` — FAIL.
- [ ] **Step 3: Implement** the five corruptions of design §5.2: numeric — scale a stated number by a factor well outside `params.rel_tolerance` keeping its format, or swap `ms` and `s`; entity — replace the service with another service of the entry, or swap caller and callee; direction — replace the direction word with the first word of the opposite list in `params.direction_words`; log quote — replace one inner word of the quote; missing citation — replace one cite with a same-prefix ID absent from the entry.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(s2.9): planted claims - one corruption per error category, each rejected by the S2.8 verifier`.

### Task 4: Labelling set builder

**Files:**
- Create: `helios/labelling/sets.py`, `bin/labelling_set.py`
- Test: `tests/labelling/test_sets.py`, `tests/test_labelling_set_cli.py`

**Interfaces:**
- Consumes: Tasks 2–3; `CoELedger` (verified before use); `get_variant(name).compute_variant_config_hash()` to map entries to arms.
- Produces: `ARMS = ("HELIOS-Full", "HELIOS-noLLM")`; `def rubric_sha(path: Path) -> str`; `def derived_seed(item_keys: Sequence[str], rubric_sha: str) -> int` (first 8 bytes of SHA-256 over the sorted keys joined by newlines, then the rubric SHA); `def rater_order(seed: int, person: str, n: int) -> list[int]`; `@dataclass class LabellingSet: items: list[dict]; key: dict[str, dict]; manifest: dict`; `def build_set(entries: Sequence[Mapping], *, planted_share: float, rubric_sha: str, params) -> LabellingSet` (item: `{"item", "header", "kind", "sentence", "cards"}`; key per item: `{"arm", "run_id", "incident_id", "slot", "index", "planted", "category", "source"}`; manifest: `{"seed", "rubric_sha", "set_sha256", "key_sha256", "counts", "ledgers"}`); `def write_set(s: LabellingSet, directory: Path) -> None` (write-once). CLI: `labelling_set.py --coe DIR [DIR ...] --out DIR --share training|confirmatory --rubric PATH`.

- [ ] **Step 1: Failing tests**: `test_set_json_never_names_arm_run_case_or_path` (scan `set.json` for arm names, run IDs, incident IDs, `data/`, `.parquet`, `.coe`); `test_seed_is_derived_and_recomputable` (rebuild → identical bytes; another rubric SHA → another order); `test_rater_orders_differ_and_cover_all_items`; `test_set_items_have_one_shape_and_planted_are_spread` (one key set for all items; no run of more than six consecutive planted items in a 400-item set); `test_odd_entries_are_skipped_and_counted` (noExpl entry, empty ranking, empty slots → `manifest["counts"]["skipped"]`); `test_write_once`; CLI: `test_cli_refuses_unverified_ledger`, `test_cli_refuses_confirmatory_entries_before_build_freeze`, `test_cli_never_opens_ground_truth` (patch `builtins.open` as the leak test does).
- [ ] **Step 2: Run** `poetry run pytest tests/labelling/test_sets.py tests/test_labelling_set_cli.py -q --no-cov` — FAIL.
- [ ] **Step 3: Implement**; item IDs are SHA-256 of (seed, source key, planted flag) truncated, so reproducible and uninformative; shuffle with `random.Random(seed)`.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(s2.9): masked labelling set with sealed key, derived seed, write-once`.

### Task 5: Agreement and H_fact analysis

**Files:**
- Create: `helios/evaluation/rater_agreement.py`
- Test: `tests/evaluation/test_rater_agreement.py`

**Interfaces:**
- Consumes: `latest()` (Task 1), the set key (Task 4).
- Produces: `def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float | None` (None when undefined); `KAPPA_THRESHOLD = 7 / 10`; `def consensus(labels: Mapping, adjudications: Mapping, key: Mapping, *, kappa: float | None) -> dict[str, dict]` (R-i/R-m: κ at or above threshold → agreements stand and disagreements take the adjudicator's label; below → the adjudicator's label for every real claim); `def h_fact(consensus, key) -> dict` (`per_arm`, `per_case` for the sign test; real claims only); `def per_rater_h_fact(labels, key) -> dict`; `def detection(labels, key) -> dict` (per person: detected share per category, false-alarm share on real claims, `below_floor` per sitting); `def agreement_report(...) -> dict` (κ all items, κ real only, category agreement, the above, blinding-check hit rate).

- [ ] **Step 1: Failing tests** with hand-computed fixtures: `test_kappa_matches_hand_value` (2×2 table 40/5/5/50 → 0.798 to 3 dp); `test_kappa_undefined_when_one_label_only` (None); `test_prevalence_paradox_fixture` (99 agree-supported, 1 disagreement → κ at most 0.01 though 99% agree); `test_consensus_above_and_below_threshold`; `test_planted_never_count_in_h_fact`; `test_h_fact_per_case_pairs_full_and_nollm`; `test_detection_floor_flags_a_sitting`; `test_category_disagreement_does_not_change_h_fact`; `test_blinding_hit_rate`.
- [ ] **Step 2: Run** `poetry run pytest tests/evaluation/test_rater_agreement.py -q --no-cov` — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(s2.9): kappa, adjudicated consensus (R-i, R-m), H_fact per arm, case and rater, planted-claim detection`.

### Task 6: Labelling server and page

**Files:**
- Create: `helios/labelling/session.py` (pure logic), `helios/labelling/page.html`, `bin/label_server.py` (HTTP wrapper and CLI)
- Test: `tests/labelling/test_session.py`, `tests/test_label_server.py`

**Interfaces:**
- Consumes: Tasks 1, 2, 4, 5.
- Produces: `class LabellingSession` built from a set directory, an `AnnotationLedger`, a people file (`people.json`: person → SHA-256 of their key, role ∈ {rater, adjudicator}) and a mode ∈ {`label`, `onboarding`}; methods `next_item(person) -> dict | None` (rater: next unlabelled item in `rater_order`; adjudicator: next queue item with the two labels unattributed in random order), `submit(person, item, verdict, category, note) -> None` (refuses unserved items, locked items, bad categories; dwell measured from serve time), `blinding_prompt(person) -> dict | None` (one already-labelled real claim after every 25 labels), `submit_guess(person, item, guess) -> None`, `progress(person) -> dict`. CLI: `label_server.py serve --set DIR --people FILE [--port N] [--mode label|onboarding]`; `label_server.py add-person NAME --role rater|adjudicator` (prints the key once, stores its hash); `label_server.py keygen` (prints an `ANNOTATIONS_ED25519_PRIVATE_KEY=` line, writes the public key, refuses if the public key file exists). HTTP: `GET /`, `GET /api/next`, `POST /api/label`, `GET /api/blind`, `POST /api/blind`; key in header `X-Label-Key`; any other path or a bad key → 404, empty body.

- [ ] **Step 1: Failing tests**: session — `test_rater_never_receives_secret_fields` (no arm, run, case, planted flag or key-file field in any `next_item`); `test_label_for_unserved_item_is_refused`; `test_two_tabs_get_the_same_next_item`; `test_revise_until_both_labelled_then_locked`; `test_adjudicator_sees_only_disagreements_unattributed` (verdict and category-only disagreements; never planted items); `test_onboarding_mode_returns_answer_after_label` (answers only in onboarding mode); `test_restart_resumes_from_ledger`; `test_tampered_ledger_refuses_to_start`; `test_blinding_prompt_every_25_labels`. HTTP — `test_server_binds_loopback_only`; `test_bad_or_missing_key_gets_404`; `test_page_and_api_round_trip` (ephemeral port in a thread; one label → one ledger entry); `test_server_needs_the_annotations_key_not_the_deviation_key`.
- [ ] **Step 2: Run** `poetry run pytest tests/labelling/test_session.py tests/test_label_server.py -q --no-cov` — FAIL.
- [ ] **Step 3: Implement**; `ThreadingHTTPServer` with one lock around session calls; page = layout B (header line, claim, evidence cards, Supported / Unsupported, category required for Unsupported, note, progress, pause), no external assets.
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `feat(s2.9): labelling server - one claim at a time, per-person keys, lock rule, adjudicator queue, blinding check, onboarding mode`.

### Task 7: Build ledgers, training and onboarding sets

**Files:**
- Create: `bin/labelling_runs.py`, `helios/labelling/training.py`
- Test: `tests/labelling/test_training.py`, `tests/test_labelling_runs_cli.py`

**Interfaces:**
- Consumes: `RunOrchestrator` (frozen parameters; narrator client as `bin/narrator_build_run.py` `_NarratorClient`, L-pipe answers from the cache only), Tasks 2–4.
- Produces: `labelling_runs.py --out DIR` writes signed CoE ledgers for HELIOS-Full and HELIOS-noLLM on both build corpora into `DIR/<corpus>-<variant>.coe/` (refuses the pool and an existing DIR; needs the CoE signing key as the runner does); `def select_training(entries, *, n_per_arm: int, seed: int, exclude_cases: set[str]) -> list[Mapping]` (every claim kind present in the candidates appears; Full and noLLM paired by case where possible); `def onboarding_set(entries, *, seed: int, params) -> LabellingSet` (about 40 items: a supported example per kind and a planted example per category; answers in the key).

- [ ] **Step 1: Failing tests**: `test_selection_covers_every_claim_kind`; `test_selection_excludes_earlier_rounds`; `test_selection_is_deterministic`; `test_onboarding_covers_each_kind_and_category`; CLI `test_runs_refuse_pool_and_existing_dir`, `test_runs_never_open_ground_truth`.
- [ ] **Step 2: Run** `poetry run pytest tests/labelling/test_training.py tests/test_labelling_runs_cli.py -q --no-cov` — FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Run the build ledgers once** (Ollama up, about 1–2 hours): `set -a; source .env; set +a; poetry run python bin/labelling_runs.py --out data/labelling/build` — Expected: four ledger dirs, each passing `verify_ledgers.py --coe`; then training round 1 and the onboarding set into `data/labelling/training-1/` and `data/labelling/onboarding/` (counts reported only).
- [ ] **Step 6: Commit** `feat(s2.9): build-data ledgers, stratified training selection, onboarding set` (code only; `data/labelling/` is gitignored).

### Task 8: Rubric, docs, review, merge

**Files:**
- Create: `docs/research/h_fact_rubric.md`
- Modify: design §10; tracking notes
- Test: `tests/labelling/test_rubric.py`

- [ ] **Step 1: Failing tests** `test_rubric_names_every_kind_and_category` (the rubric mentions each claim kind and each category id) and `test_rubric_sha_matches_the_set_manifest` (`rubric_sha(path)` equals the manifest's `rubric_sha` for a set built from a fixture with that rubric).
- [ ] **Step 2: Write the rubric** per design §5.1 with two worked examples per kind from the build ledgers (one supported, one planted with its category and reason) and the listed edge cases; marked draft until training reaches κ ≥ 0.7.
- [ ] **Step 3: Run** the tests — PASS; full local gate (root CLAUDE.md sequence) — exit 0.
- [ ] **Step 4: Design §10** (built, builder's decisions, test evidence, training status); fresh whole-branch review on the most capable model with this Review Focus; fixes test-first; owner go-ahead → local `--no-ff` merge. Row S2-M7-RES01 stays IN_PROGRESS (rater training pending; the S2 exit report carries it with owner and date).

## PR 2 — training (after rater 2 is confirmed; owner-led)

- Owner: generate the annotations key (`label_server.py keygen`), store it in `.env` and the password manager, commit the public key; add the three people; open the tunnel.
- Onboarding sitting per rater; training round 1 (50 narratives); `agreement_report`; disagreement review without the owner (R-l); rubric revisions committed with their hashes; further rounds until κ ≥ 0.7; freeze the rubric hash; draft the deviation entry of design §6 for owner approval; row DONE.
