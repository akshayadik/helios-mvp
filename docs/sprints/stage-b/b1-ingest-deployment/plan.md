# B1 Ingest and deployment · plan

**Milestone:** S3-M13 · **Exit tag:** `rb-b1-exit` (proposed) · **Status:** planned; starts early, alongside phases E and A (chair call, 26 Nov 2026, item 6) · **Effort:** about 6 working weeks for the module contents (chair call §5.2), plus about 3–4 working weeks for the quality items below

Parent plan: [`../plan.md`](../plan.md). Task details move into `docs/tracking/helios_task_breakdown.md` § Stage B, with tracker rows, when B1 opens; until then this plan is the working list.

## Goal

Make the product run on live telemetry and deploy it, and first fix the component weaknesses that the Stage A build rehearsal exposed, so that the live product is not built on top of them.

## Rules

- Built on `main` behind feature flags (`VCLFlag`), through the same gate. The frozen evidence build (`build-freeze-5`, used by E1–E3 from `../helios-e`) is never touched.
- **No tuning on the confirmatory pool.** Every quality item below is designed and checked on build corpora, the OTel captures, AIOpsLab and captures made after `build-freeze`. Pool results (E1 onwards) are never used to choose a design, a threshold or a prompt.
- A change that alters what a pre-registered measure reads (state, confidence, CpR, rankings) is a **Stage B variant**: its own flag, a design note first, and an exploratory evaluation pre-registered in the Stage B pre-registration. It never replaces HELIOS-Full's Stage A build.
- **Phases E and A come first.** No B1 job runs while an E2, E3 or rerun campaign is running (timed measures need a free machine). B1 work fits between campaign nights.

## Part 1 · Quality items from the Stage A rehearsal

Evidence below is from the RCAEval build rehearsal (`docs/sprints/a-analysis/phase_a_tooling.md` §5) and the component review backlog (`docs/sprints/s5-integration-freeze/component_review_backlog.md`). Order is the order of work.

### Q1 · Confidence that separates right from wrong, and state labels that rank reliability (MAHC)

**Backlog:** CR-03b, CR-03c, CR-05 · **Flag:** `mahc_hierarchical` plus a new Stage B flag per change · **Effort:** 4–5 working days

**Why.**
- Full's confidence is well calibrated but compressed: mean 0.964 against an observed HR@3 of 0.968, ECE 0.011, AUROC only 0.718. noRouter reaches 0.815, so routing loses some of the signal.
- The labels do not rank reliability: "confirmed" reads 0.956 (n 180), while "provisional: one pipeline ran" reads 0.981 (n 266). CR-03 option A fixed only the wording.

**Steps.**
1. Write a design note comparing CR-03b (raise the CONFIRMED floor), CR-03c (a confident router stop may publish CONFIRMED), and a confidence term for pipeline disagreement or evidence spread (CR-05).
2. Build the chosen changes behind new flags.
3. Replay the build corpora and OTel captures, reading the result per state and per variant.

**Done when.**
- On non-pool data, CONFIRMED's HR@3 is at least that of each PROVISIONAL reason.
- AUROC is above the frozen build's on the same cases.
- HR@3 is within one percentage point of the frozen build (the S3.1 tolerance).
- The Stage B pre-registration names the variant and its comparison.

### Q2 · A claim verifier that is shown to catch false claims (evidence-grounded narratives)

**Backlog:** new item (proposed CR-24) · **Flag:** `coe_narrative` · **Effort:** about 3 working days

**Why.**
- On build data the verifier rejected none of the drafted claims, for every narrating variant. It cannot tell apart "the narrator never invents" from "the verifier never looks".
- The Full narrator needs 2.2 model attempts per narrative.

**Steps.**
1. Build a planted-error test set from build narratives: wrong service, wrong metric, wrong time window, a number not in the evidence, and a causal claim with no supporting edge.
2. Measure the verifier's catch rate per error type, and its false rejections on the original claims.
3. Tighten the matching rules where it misses.
4. Add a structured-output check before a model retry, to cut attempts.

**Done when.**
- The catch rate per error type is reported, and every type is caught in most planted cases.
- False rejections on the original claims stay rare and are reported.
- Attempts per narrative fall, with grounding unchanged on the original claims.

### Q3 · Parse each case's traces once (ingestion and pipeline inputs)

**Backlog:** new item (proposed CR-25; Stage B backlog "share parsed traces across variants") · **Flag:** new implementation flag (shared trace cache) · **Effort:** 3–4 working days

**Why.**
- E1 took about 13.5 h against a projected 2.5 h. Every variant re-reads and regex-parses the same large trace files (pool windows carry `p2_traces.parquet`, median 15.5 MB, up to 56 MB). The build corpora carried no traces, so the projection could not see the cost.
- In live use, the same parse cost sits on the triage path.

**Steps.**
1. Profile one trace-heavy window: an OTel capture, or a non-pool RCAEval window with traces.
2. Parse spans once per window into a columnar cache keyed by the window's content seal.
3. Replace per-span regex with vectorised parsing, keeping one shared rule for span status (entry 104, `helios/telemetry/span_status.py`).
4. Share the cache across variants within a campaign.

**Done when.**
- With the flag on and off, every build window and OTel capture gives identical rankings, evidence rows and narratives.
- The speed-up per run is measured and reported. The design note sets the target before work starts.

### Q4 · Answer with the data that is present (orchestrator and pipelines)

**Backlog:** new item (proposed CR-26) · **Flag:** new Stage B flag · **Effort:** about 3 working days

**Why.**
- 990 of the 1,229 excluded RCAEval build run keys were excluded for an absent modality.
- A production incident with no logs or no traces should still get a ranked answer from the pipelines that can run.

**Steps.**
1. Run the pipelines whose inputs exist.
2. Mark the result as partial, naming the missing modality.
3. Lower the confidence through the Q1 mechanism.
4. Keep the exclusion rule unchanged for the frozen build and its variants.

**Done when.**
- Build cases that the frozen build excludes now return a partial answer under the flag.
- Their HR@3 is reported separately.
- Partial answers never publish CONFIRMED.

### Q5 · Baseline adapters that do not fail (Family B comparison systems)

**Backlog:** CR-18, CR-23, and the 239 baseline-error exclusions in the build rehearsal · **Effort:** 2–3 working days

**Why.** Baseline errors weaken the Family B comparisons. They are the comparison systems, not HELIOS.

**Start condition.** **After E2 has finished.** Any change before then would make Family B compare against different baselines than the ones registered.

**Steps.**
1. Group the build baseline errors by baseline and input shape.
2. Harden the adapters.
3. Record each change as a Stage B baseline version.

**Done when.** Each error group has a fix or a documented reason it cannot be fixed. Stage A tables keep the frozen baselines.

### Q6 · Analysis output carries its own provenance (`bin/analyse.py`)

**Backlog:** S4.11 T-j · **Effort:** about half a working day

**Why.** The analysis JSON does not record its input digests, the plan hash or the BCa seeds. The Phase A bundle records them beside it.

**Steps.** On `main`, add the three fields to the analysis JSON. Phase A keeps using the frozen `bin/analyse.py` and the bundle.

**Done when.** The fields are present and tested on `main`.

### What stays as it is

**Cheap-first routing.** On the build rehearsal it saves 47.7% of pipeline tokens and cuts median TTT from 9,272 ms to 228 ms. HR@1 changes by −0.008 and HR@3 by −0.006. Its next step is the shadow go-live in Part 2.

## Part 2 · Module contents (broken into tasks when B1 opens)

| Item | Source |
|---|---|
| Live OTLP ingest (`ingest_mode` live) | Stage B plan, B1 |
| P4 cognitive telemetry: MCP spans, goal drift, loop depth | Stage B plan, B1 |
| P5 business telemetry | Stage B plan, B1 |
| Helm production deployment | Stage B plan, B1 |
| Multi-tenant administration | Stage B plan, B1 |
| Router go-live in shadow mode (uniform routing live; the frozen router's choices recorded; switch on per system within one point of HR@3) | Stage B plan, carried in from S3.1 |
| Record an AIOpsLab problem set (pinned images and charts) for B5 | Stage B plan, carried in from S1.3 |

Q3 and Q4 come before live ingest, because live ingest puts the trace parse on the triage path and receives incomplete telemetry as a matter of course.

## Sequence

1. Q1, Q2 and Q3 (core; between E2 and E3 campaign nights).
2. Q4.
3. Q6, at any point (small).
4. Q5, after E2.
5. Part 2, starting with live ingest.

## Risks

| Risk | Mitigation |
|---|---|
| B1 competes with phases E and A for time and the machine | Phases E and A come first; no B1 job runs during a campaign |
| A quality fix is tuned, knowingly or not, to the pool | Design and check on non-pool data only; pool results are never read for B1 |
| A Stage B change leaks into the frozen build | Separate flags; campaigns run only from the `build-freeze-5` checkout, and `run` refuses any other build |
