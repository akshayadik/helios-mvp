# S2.8 — Narrative Engine with grounding verifier · design

**Task:** S2.8 (tracking S2-M7-ENG08) · **Date:** 2026-10-31 · **Status:** draft for owner approval (builder check done 2026-10-31) · **Depends on:** S2.7 (CoE entry and evidence namespace, entry 64), S2.5 (fused verdict), S2.3 (L-pipe model, cache, aliases, entries 57–58) · **Owner decisions:** marked *owner* (2026-10-31)

**Flag:** `VCLFlag.COE_NARRATIVE` gates the Narrative Engine (OFF = the ranked list only, HELIOS-noExpl). Which narrator writes is decided by `l2c_llm`: on → the LLM narrator; off → the template narrator. The verifier runs on every narrative.

## 1. Intent

The CoE entry (S2.7) records every decision and the evidence behind it; nobody reads JSON at 3 a.m. S2.8 turns one entry into a short incident narrative an on-call engineer can trust: what happened (story), where the pipelines disagree and why (contradictions), and what to check next (verification steps). It is IN1, evidence-grounded narratives.

The owner's rule *(owner)*: **every displayed claim cites evidence that exists and supports it.** A deterministic verifier enforces this by code; nothing unsupported reaches the engineer.

## 2. Decisions already made

| # | Decision | Who |
|---|---|---|
| N-a | **HELIOS-noLLM, HELIOS-D and HELIOS-G use a deterministic, rule-based template narrator; an LLM never writes a narrative for them.** An LLM narrator there would contaminate the baseline (S2-BL-15) | owner, 2026-10-31 |
| N-b | **Typed claims, free wording under containment.** The narrator emits typed claims and writes each sentence itself; the verifier checks the typed fields against the cited items and enforces containment on the sentence: only the claim's services may be named (caller and callee for call-structure claims); every number must be in a cited item; direction words must agree with the claim's direction | owner, 2026-10-31 |
| N-c | **Log claims carry a verbatim snippet** that must occur in the cited `L:<worker>:<line>` text. **Call-structure claims carry caller and callee**, checked against the directed edge in the cited G-pipe item | owner, 2026-10-31 |
| N-d | **Failure handling per slot, never by cutting sentences:** a slot with a rejected claim gets one retry at temperature 0 with the rejection reasons in the prompt; if it fails again the slot is replaced by the template narrator's text for that slot and a fallback event is logged | owner, 2026-10-31 |
| N-e | **Raters label the displayed (post-verifier) narrative; H_fact is judged against the cited evidence only.** The ground-truth clause is removed from H_fact (metric contract §5, task S2.9 step 1): a wrong culprit is a ranking error (HR@k), not a hallucination. Raters never see the fault label. Deviation entry and OSF addendum before any confirmatory narrative (§6) | owner, 2026-10-31 |
| N-f | **Numbers are normalised before comparison:** percent ↔ fraction, ms ↔ s, "~" / "about" allowed; equal within ±1% relative or at the precision the sentence states | owner, 2026-10-31 |
| N-g | **Verification steps** are accepted only if: the target is a fused top-3 suspect, or its caller or callee through a cited G-pipe edge; any time lies inside the incident window around the trigger; the verb is from a frozen read-only list (query, inspect, verify, check, filter); the modality matches the cited item (D → metric, L → log or trace, G → edge or connection); at least one citation. Fallback: the template's step for the top suspect | owner, 2026-10-31 |
| N-i | **Raw before/after levels in the evidence.** D-pipe's `coe_evidence` gains, per top-5 service and channel, the median level before and after the trigger with its unit, from the series D-pipe already reads; additive (ranking, μ, σ, decision hash unchanged and re-pinned); the CoE items `D:<svc>:<channel>` carry them, so sentences can state concrete levels and N-f's normalisation applies | owner, 2026-10-31 |
| N-h | **Machine verification report** beside the rater labels, with no human labour: first-pass acceptance rate, rejections by failure mode, retry success, slot fallback rate, per variant | owner, 2026-10-31 |

Carried from S2.3 §5.5: the contradiction list is computed by code (the narrator explains it, never finds it); `primary_culprit`, μ, σ and confidence are filled by code; the narrator never changes a ranking or states a number the code did not supply.

## 3. Goals, non-goals, anti-goals

**Goals.** A template narrator; an LLM narrator on the frozen L-pipe model; one typed-claim schema for both; a deterministic claim parser and verifier; slot retry and fallback; the narrative stored with the run and in its CoE entry; the verification report; a dev-split prompt round and a frozen narrator prompt.

**Non-goals.** The rating rubric and labelling tool (S2.9); remediation that changes a system (Stage B, L4); a UI beyond rendered text; changing any ranking, fusion or confidence.

**Anti-goals** — it fails even if it runs:

- An LLM call in a run with `l2c_llm` off (N-a). A test asserts that noLLM, D and G make no model call.
- A displayed claim the verifier did not accept, or a displayed sentence without a citation.
- A number, service, direction or log text in a displayed sentence that the cited items do not hold.
- A narrative that reads a ground-truth field, fault label or injection time.
- A narrator output that changes the ranking, μ, σ, confidence or state.
- Template text that is recognisable by style at a glance — it uses the same sentence shapes the LLM prompt asks for (S2.9 blinding).

## 4. Constraints

- The narrator reads **only the CoE entry** of the run (S2.7 C-b: the single citation source), plus the window's start time for wall-clock rendering. It never reads raw telemetry or the store.
- Citations use the S2.7 IDs (`D:cart:latency`, `G:payment:wait_from`, `L:log:L12`). L-pipe worker claims (`L:<worker>:claim<n>`) are **not citable**: they are model output, not evidence *(my call: citing them would let one model's claim ground another's)*.
- Same model, digest and cache as L-pipe (llama3.1:8b, `46e0c10c039e…`, `ResponseCache`); one call per slot attempt, one at a time; the narrator prompt is frozen by SHA. The retry prompt includes the rejection reasons, so it is a deterministic function of the first answer and is cached like any call.
- Real service names in the narrator prompt and output *(my call: the CoE entry and the engineer use real names; the leak-sensitive inputs — fault names, case names, injection time — are already absent from the entry, and the alias layer protected L-pipe's ranking, which the narrator cannot change)*.
- Narrator tokens count in CpR (token component); narrator time is recorded but does not count in TTT, which is first publication of the ranking (entries 46, 60).
- Never read pool data before `build-freeze`; prompt development uses the build dev split only.

## 5. Design

### 5.1 Output

A narrative has three slots, each a list of typed claims, plus the code-filled header:

- **header** (code only): fused top-3 with confidence and state; never written by a narrator.
- **story**: what happened, in order.
- **contradictions**: one item per entry in the CoE `F.disagree` list.
- **verification**: up to 3 read-only checks.

Stored as JSON (claims with kinds, fields, cites, sentence, verdict) and rendered text (sentences with their citation IDs in brackets).

### 5.2 Claim kinds

| Kind | Fields | Accepted when |
|---|---|---|
| `shift` | service, channel (error / latency / resource), direction (up / down), cites | a cited `D:<service>:<channel>` item exists with a shift of that sign; or a cited L line for that service |
| `call_structure` | caller, callee, feature (wait / lead / ghost edge), cites | a cited `G:<callee>:wait_from` (or `leads`, `ghost_edges`) item holds that directed edge |
| `log_message` | service, snippet, cites | the snippet occurs verbatim in a cited `L:<worker>:<line>` text of that service |
| `ranking` | service, rank, cites | the service holds that rank in the fused ranking; cites the `F` step |
| `contradiction` | pipeline, service, cites | the pipeline is in `F.disagree` with that top-1 service; cites at least one item of that pipeline for that service |
| `verification_step` | target_service, action_verb, modality, time window, cites | N-g |

For every kind, the sentence passes containment (N-b, N-f). Direction words come from a small frozen list per direction; the time window and every wall-clock time in a sentence must lie inside the incident window around the trigger.

### 5.3 Template narrator

Deterministic code over the CoE entry, emitting the same typed claims:

- story: the top suspect's rank claim; its largest D-pipe channel shift; its G-pipe wait or lead edge if present; its first cited log line (verbatim snippet) if present; then the same for suspects 2–3 where they have evidence;
- contradictions: one claim per `F.disagree` pipeline, citing that pipeline's strongest item for its top-1;
- verification: one step per modality present for the top suspect, window = the incident window.

Sentence shapes match what the LLM prompt asks for. The template output passes the verifier by construction (a test asserts it on every build case).

### 5.4 LLM narrator

One call per slot, the prompt holding the CoE entry's items, the code-filled header, the disagree list and the claim schema; JSON out. Parse → verify → on any rejection, one retry with the reasons → on a second rejection, the template slot (N-d). A parse failure is a rejection of the whole slot. No ranking, empty CoE items or a gated-off narrator → template only.

### 5.5 Verifier and report

A pure function `verify(claim, entry, window) → (accepted, reason)`; failure reasons are a closed set (`missing_cite`, `unknown_id`, `kind_mismatch`, `wrong_direction`, `wrong_edge`, `snippet_not_found`, `foreign_service`, `number_not_in_evidence`, `time_out_of_window`, `verb_not_allowed`, `modality_mismatch`, `rank_mismatch`, `not_in_disagree`, `schema`). The verification report (N-h) is computed from stored narrative rows.

### 5.6 Storage and the CoE entry

A `narrative_row` table (run, narrator kind, slots JSON, rendered text, attempts, fallbacks, tokens); the narrative is added to the run's CoE entry as a step `N` before the entry is appended, so the displayed narrative is part of the signed record and the verifier can be re-run from the ledger alone.

### 5.7 Prompt development and freeze

Like S2.3: at most 3 prompt rounds on the build **dev** split (`split_cases`), measured by the verification report only (no ground truth); the owner chooses; a final run on the held-out split; the prompt SHA is frozen in a deviation entry. A provisional prompt is refused in confirmatory runs.

### 5.8 Builder-check answers (2026-10-31)

- **G-pipe edges.** Call direction is caller → callee throughout. `G:<s>:wait_from` maps caller → wait share for edges into `s` (caller = the key, callee = `s`; the share is citable as a number). `G:<s>:leads` lists callers whose shift `s` preceded (edge caller → `s`; the claim says `s` moved first). `G:<s>:ghost_edges` holds `[caller, callee]` pairs as stored.
- **Raw levels (N-i).** Units come from a fixed map per metric source, recorded with the value: OTel span-metric latency in ms; error channel as errors per step (a count, not a rate); RCAEval and resource series in the dataset's own unit, labelled by metric name (e.g. `latency-90`, `cpu`) when no unit is known — the narrator then states the value with the metric name and no converted unit. N-f's ms ↔ s and percent ↔ fraction apply only where the unit says so.
- **Shift direction** is the sign of the cited channel's value; for `resource`, up = more use (CPU, memory, connections). Only the three channel items (error, latency, resource) ground a `shift` claim; score, propagation and final are citable for `ranking` claims only.
- **Incident window.** The S2.7 `T` step gains `window_start` and `window_end` (ISO, from the TelemetryWindow) so the verifier can be re-run from the ledger alone; times in sentences are wall-clock UTC inside that window. These are capture bounds, not fault data (the leakage test still checks for injection times) — an additive CoE field recorded in entry B.
- **Order in the runner.** Build entry → narrate (N added to the entry) → store rows → append. A model error inside the narrator never fails the run: the slot falls back to the template. Step `N` carries `cost` (narrator prompt and completion tokens, replayed from the cache, so deterministic) and `measured` (narrator wall time).
- **Slots and calls.** A slot with nothing to say (empty disagree list; no evidence beyond the header) makes no model call: 1–3 calls per narrative plus retries. Retry and fallback apply to the whole slot (N-d), so a slot is all-LLM or all-template.
- **Variants.** Every variant with `coe_narrative` on gets a narrative (all except noExpl); the LLM narrator runs iff `l2c_llm` is on, even when L-pipe failed or abstained (it then has no `L:` items to cite). Tests cover noLLM, D, G (no model call), Full, LLM-only and noExpl.
- **Unchanged ranking** is structural: the header is filled by code from `F`, and nothing reads narrator output back into the verdict, fusion or scoring path (test: fused row and verdict hashes equal with the narrator on and off).
- **Style blinding** is checked, not assumed: both narrators render through one renderer (same sentence slots and citation format); the report includes sentence-length and claims-per-slot distributions per narrator so a style gap is visible before S2.9.
- **Frozen lists.** Direction words, the verb list and the numeric tolerance live in `data/frozen/narrator_params.json`, hashed and frozen with the prompt SHA in entry C; a provisional file is refused in confirmatory runs like the other parameter files.

## 6. Protocol records

- **Entry A (before merge of PR 1): H_fact definition (N-e).** Clause: metric contract §5; task S2.9 step 1; Ch3 A-H7. Change: remove "and — for root-cause claims — agrees with the ground truth"; a claim is supported iff it cites an existing CoE item that substantiates its entity, direction, magnitude (within tolerance) and, for log claims, its verbatim snippet; diagnostic accuracy is measured by HR@k only; raters label the displayed narrative and never see the fault label. Analytic consequence: A-H7's measure changes; Full and noLLM are both verifier-checked, so their H_fact are expected to be close and the predicted direction may not hold; the sign test runs as registered; OSF addendum line required before any confirmatory narrative (S2-BL-05).
- **Entry B (before merge of PR 1): the narrator rules** — N-a…N-i, claim kinds, citable items, real names, CpR/TTT treatment, storage in the CoE entry (step `N`), the additive CoE fields (D-pipe raw levels; `T.window_start`, `T.window_end`), frozen narrator parameter file.
- **Entry C (PR 2): narrator prompt frozen** (SHA, round chosen, report figures).

## 6a. Size and tracking

The plan gives 2½ days; with typed claims, containment, retry/fallback, raw levels and a prompt round my estimate is **4½**. Row S2-M7-ENG08. Two PRs: (1) schema, template narrator, verifier, LLM narrator with a provisional prompt, storage, report; (2) prompt rounds and freeze.

## 7. Done when

- Every displayed claim cites an existing item and was accepted by the verifier (test over all build cases).
- noLLM, D and G make no model call (test); noExpl shows the ranked list only.
- The template narrative passes the verifier on every build case.
- Each failure reason has a test that produces it; containment catches a foreign service, an unsupported number and a wrong direction word.
- Retry and fallback paths tested with a fake model; the narrative is in the CoE entry and the ledger verifies.
- Verification report produced on the dev and held-out splits; prompt frozen with an entry.

## 8. Calls I made (owner to check)

1. Worker claims (`L:<worker>:claim<n>`) are not citable; only evidence lines and numbers.
2. Real service names in the narrator prompt (no aliases).
3. Narrator tokens count in CpR; narrator time does not count in TTT.
4. The narrative is stored in the CoE entry as step `N` (part of the signed record) and in a `narrative_row` table.
5. One LLM call per slot (three per narrative, plus retries).
6. No fused ranking → template only, no model call.
7. Up to 3 verification steps; story covers suspects 1–3 only.
8. Prompt rounds measured by the verification report, never by ground truth.

## 9. Left to the builder

Exact template sentences (within the shapes the prompt asks for); the direction word lists; the prompt text of round 1; table column names; how rendered citations look.

## 10. Results

(Filled after the build.)
