# S2.3 — Lean multi-agent L-pipe · design

**Task:** S2.3 (tracking S2-M7-ENG03) · **Date:** 2026-10-30 · **Status:** approved by the owner 2026-10-30 (§5.8 build-data counts corrected the same day: 120 of 495 RCAEval build cases have logs) · **Depends on:** S1.8 verdict contract, S2.1 frozen trigger and detector (entry 52), S1.4 log templates, S2.2 span features and G-pipe evidence (entries 54–56) · **Owner decisions:** the points marked *owner* below (2026-10-30)

## 1. Intent

L-pipe is the third peer pipeline. D-pipe sees numbers, G-pipe sees call structure; **L-pipe reads what the telemetry says** — log messages, error attributes, the shape of metric shifts — and decodes it semantically ("connection pool exhausted" is not "connection refused"). The owner's four capabilities *(owner)*:

1. a cohesive mechanical narrative of the incident;
2. semantic decoding of unstructured telemetry;
3. explicit resolution of contradictions and ambiguity;
4. bounded verification steps an engineer can run.

Examiner criteria *(owner)*: **strict grounding** (every claim traceable to a telemetry line) and **cognitive acceleration** (the operator reaches the cause faster than reading dashboards).

These capabilities split across two components *(owner, "go with that split")*:

- **L-pipe proper** (this task): three workers read raw telemetry of one modality each and produce an **independent** ranking with (μ, σ). It never sees D-pipe or G-pipe output, so HELIOS-LLM-only measures the LLM alone and MAHC (S2.5) does not count D and G evidence twice.
- **The narrator** (built in **S2.8**, the Narrative Engine, which the task breakdown already gives the narrator and its grounding verifier, IN1): reads the fused ranking and all three pipelines' evidence, and writes capabilities 1, 3 and 4. What this design settled about it is carried to S2.8 in §5.5.

Today's L-pipe (`helios/pipelines/l_pipe/`, 457 lines) sends one prompt (`rca_v1`) with only the list of service names; it has no telemetry content, no μ and no σ.

## 2. Decisions already made

| # | Decision | Who |
|---|---|---|
| L-a | **Split:** workers rank from raw telemetry only; a post-consensus narrator reads D/G/L evidence and writes the story, contradictions and verification steps; S2.8 checks grounding; S2.5 fuses | owner, 2026-10-30 |
| L-b | **The orchestrator is deterministic code**, not an LLM. It merges, computes μ and σ, drops invalid workers and lists contradictions; no model call adjudicates | owner, 2026-10-30 |
| L-c | **Equal weights, fixed now:** each valid worker weighs 1/k, k = number of workers whose output passes the schema and citation checks. No weights are fitted, so there is no selection run | owner, 2026-10-30 |
| L-d | **k = 0 → L-pipe abstains**; S2.5 fuses D and G only. **k = 1 → σ is at its maximum** (one opinion carries no evidence of agreement) | owner, 2026-10-30 |
| L-e | **Inside L-pipe, a claim survives only if it cites lines that exist in that worker's own digest.** Checks against D-pipe and G-pipe evidence belong to S2.5 and S2.8, never to L-pipe | owner, 2026-10-30 |
| L-f | **The trace worker is skipped on RCAEval-format data** (the confirmatory pool): no component meets a data format in a confirmatory run that it was not validated on in build data, as for the detector. It is built and tested on the 63 OTel v3 cases; on the pool, confirmatory L-pipe uses metrics and logs only (k ≤ 2). Running it on the pool is an exploratory sensitivity analysis after `build-freeze` | owner, 2026-10-30 |
| L-g | **Timeouts in confirmatory runs only catch hangs** (fixed, generous); every dropped worker is logged in the evidence. A tight timeout would make results depend on machine load. In production the timeout is a setting | owner, 2026-10-30 |
| L-i | **Service names are aliased in every prompt** (`svc-07`), as the task breakdown says ("only opaque IDs in prompts"): the benchmark systems are public, so a real name lets the model answer from memory of the benchmark rather than from the telemetry (A-H2, strict grounding). The alias map is stable across the workers of one incident and differs between incidents; masking reaches log bodies, stack traces, status messages and URLs. Workers and the merge work on aliases; code maps back to real names only after L-pipe's verdict, so S2.5, S2.8 and the operator see real names | owner, 2026-10-30 |
| L-h | **Where the production items go:** size-capped digests, citation pruning, structured payload → S2.3; tiered invocation (no LLM for low-severity incidents) → S3.1 cheap-first router; multi-tenancy, graph store, APM deep-links, PagerDuty/Slack → Stage B | owner, 2026-10-30 |

## 3. Goals, non-goals, anti-goals

**Goals.** Three workers (metric, log, trace) with Persona Profiles; deterministic digests; deterministic merge with μ and σ; every prompt SHA-registered; model identity pinned; L-pipe verdicts and worker outputs stored as evidence; build-data HR@3 reported (exploratory).

**Non-goals.** Fusion (S2.5); the narrator and its grounding verifier (S2.8); P4 cognitive telemetry — `p4_cognitive` is visibility of agent self-telemetry (MCP spans, goal drift, loop depth; Stage B1), not the Persona Profiles; routing (S3.1); remediation commands that change a system (Stage B, L4); RAG over runbooks or change events (Stage B); fitting weights or prompts to a score target.

**Anti-goals** — it fails even if it runs:

- L-pipe's ranking depends on D-pipe or G-pipe output (breaks L-a and A-H2).
- A prompt carries anything that identifies the answer: the case ID, a file path, a fault name, the injection time.
- σ comes from the model's own stated confidence.
- A rerun of the same incident gives a different verdict.

## 4. Constraints

- Model `llama3.1:8b` via Ollama, Protocol A (temperature 0, top_k 1, seed 42) — unchanged; `lpipe_config.py` constants change only with a deviation entry.
- Machine: Apple M5 Pro, 64 GB; measured about 53 tokens/s output; one worker call with a ~2,000-token digest is about 7–10 s.
- Candidate set = the in-scope services (`helios.telemetry.scope`), **not** the UEG-C nodes: HELIOS-LLM-only turns `l2b_graph` off.
- The window is split at the frozen trigger, as in D-pipe and G-pipe. No injection time ever.
- Build data only (D11): the 63 OTel v3 cases and the RCAEval build corpus. The pool stays locked.
- `TelemetryWindow`, sealed manifests, `metric_contract.md`, `research/osf/*`, `variants.py` and the seed register are not edited.

## 5. Design

### 5.1 Persona Profiles

A frozen registry of three profiles, each naming: the one stream it may read (P1, P3 or P2), its digest builder, its prompt ID, its digest token cap. **No worker has tools**; the "permission" is enforced in code — a worker's digest builder is the only thing that opens a stream, and it opens only its own. A test asserts each builder touches only its stream.

### 5.2 Digests (deterministic code, no LLM)

Each digest is a list of lines, each with a stable evidence ID (`M3`, `L12`, `T7`, numbered in a canonical order), restricted to candidate services, split at the trigger, timestamps written **relative to the trigger** ("+90 s").

- **Metric:** per service, the series with the largest robust shift after the trigger (the detector's robust scale), with direction and size.
- **Log:** per service, Drain templates (S1.4) that are new after the trigger or whose rate rose most, with counts before/after, severity, and one masked example body.
- **Trace (OTel only, L-f):** per service, error-span counts and status messages, and the operations whose latency rose most (S2.2 span features).

Lines are ordered by shift size and cut at the token cap; the number of lines cut is recorded. The incident is named by its opaque ID only.

**Aliasing (L-i).** After a digest is built and before it is rendered:

- The alias order is a permutation of the candidate services derived from a hash of the opaque incident ID: deterministic, different per incident, and no seed (the seed register is not touched).
- Every spelling of a service name is replaced — the scope-key stem and its case, hyphen and suffix variants (`checkout`, `checkoutservice`, `checkout-service`, `CheckoutService`), including inside URLs, RPC names (`hipstershop.CheckoutService/PlaceOrder`), hostnames and stack frames. Names of out-of-scope components (databases, caches, the collector) are aliased the same way (`dep-02`), so "redis" cannot point at a cart service.
- A post-mask check refuses to send a prompt in which any real service or component name of the window survives.
- **Residual cue, stated not hidden:** operation and message words (`Charge`, `PlaceOrder`, "card declined") still carry meaning. Removing them would remove the semantic decoding L-pipe exists for; the report says so.

### 5.3 Worker prompt and output

One prompt per worker (registered, SHA-pinned). Output JSON: up to 5 ranked services from the candidate list, and for each a short claim citing evidence IDs.

Validation, in order: JSON schema; services in the candidate set; each ranked service keeps at least one claim whose citations all exist in **that worker's** digest — otherwise the service is dropped from the list (L-e). One retry on schema failure (existing `LPIPE_MAX_RETRIES = 1`). A worker with an empty list after validation, a timeout or a malformed answer is **invalid**, with the reason recorded.

### 5.4 Merge, μ and σ (L-b, L-c, L-d)

- Each valid worker gives the service at rank r (r = 1…5) the score (6 − r)/5; unlisted services get 0.
- Merged score = mean over the k valid workers. Ties break by service name.
- **μ** = the top-1 share of the merged scores (the existing `top1_share`).
- **σ** = 1 − agreement × gap, the same shape as D-pipe and G-pipe: gap = (s1 − s2)/s1 of the merged scores; agreement = (workers whose top-1 is the merged top-1, minus one) / (k − 1) for k ≥ 2, and 0 for k = 1, so σ = 1 at k = 1.
- k = 0 → status ABSTAINED, no candidates, μ and σ None (the verdict contract), with each worker's drop reason in the evidence.

### 5.5 Narrator — carried to S2.8

S2.8 needs the fused ranking (S2.5) and one citation-ID scheme across D, G and L evidence; D-pipe stores no evidence rows yet. Building the narrator here would fix a format S2.8 then has to change, so it moves to S2.8. Settled now and carried there:

- A **contradiction list computed by code** (at least: pipelines whose top-1 differ); the narrator explains each item, it does not find them.
- Fixed output slots — `story`, `contradictions`, `verification` (read-only checks: which query, dashboard or log search confirms the suspect) — every sentence citing evidence IDs; JSON plus rendered text.
- `primary_culprit`, μ and σ are **filled by code**; the narrator never changes a ranking, μ or σ, or states a number the code did not supply.
- Open for the S2.8 design: what HELIOS-noLLM, -D and -G show (they keep `coe_narrative` on, and S2.9 rates noLLM narratives). An LLM narrator there would put a model into "no LLM", so the likely answer is a template narrative built from the evidence without a model — also the production degraded mode when L-pipe abstains.

### 5.6 Determinism and cost

- Calls run **one at a time** (parallel batching in Ollama can change outputs). The model's Ollama digest is recorded with the prompt SHAs and checked at run start.
- **Response cache:** keyed on (model digest, prompt SHA, rendered-input SHA). The workers' inputs do not depend on the variant, so the eight variants reuse one set of worker calls per incident. The cache stores each call's usage **and its measured wall time** and replays both, so CpR, latency and TTT count every call as if made; each verdict records whether it was served from the cache.
- Rerun equality: the same incident twice (cache off) gives bitwise-equal verdicts.

### 5.7 Records

L-pipe writes an `evidence_row` (as G-pipe does): the digests' line IDs and text, each worker's raw answer, validation result and drop reason, the merged scores. S2.4 counts schema-validation results from it.

### 5.8 Build data and prompt revisions

- Build data: the 63 OTel v3 cases (three workers) and the sealed RCAEval build corpus (S1.1, 495 cases, no traces; 120 have logs). L-f applies by format, so RCAEval cases have k ≤ 2 like the pool: the 120 with logs give S2.5 k = 2 data to calibrate σ on; the other 375 run the metric worker alone (k ≤ 1, σ = 1).
- Each corpus is split once into a **dev** and a **held-out** part by a hash of the opaque incident ID (no seed needed). Prompt revisions are judged on dev only; the reported HR@3 is the held-out part's, with dev beside it.
- Budget: one full build run is 63 × 3 + 120 × 2 + 375 × 1 ≈ 800 calls × ~8 s ≈ 2 hours.

## 6. Protocol records

- **Entry before prompt work** (owner reviews, then signs): L-a…L-g, the digest rules, the merge and σ formulas, the prompt-revision budget (§8). Signed before any worker sees a build case, so the rules are fixed before results exist.
- **Freeze entry** (after the build-data runs): prompt SHAs (three workers), model name and Ollama digest, digest caps, cache key. Also replaces `rca_v1`.
- L-f changes what the confirmatory L-pipe measures (two modalities on the pool); it goes in the pre-registration addendum with the next OSF deposit, not into `metric_contract.md`.

## 6a. Size and tracking

The plan gives S2.3 3 days; my estimate is **4** (the digests are most of the work; the cache adds some). Same row S2-M7-ENG03; the S2 slack absorbs it. Two PRs as in S2.2: PR 1 = profiles, digests, workers, merge, cache, tests, pre-work entry; PR 2 = build-data runs, prompt freeze, freeze entry.

## 7. Done when

- Worker verdicts and drop reasons logged per incident.
- The leakage test still passes and is extended: no rendered prompt contains a case ID, file path, fault name, injection time or real service or component name; no digest builder opens a ground-truth file.
- Prompt SHAs and the model digest frozen in the registry.
- Rerun equality on a sample of build cases.
- Build-data HR@3 of L-pipe and of each worker, and seconds per incident, reported (exploratory).

## 8. Calls I made (owner to check)

1. **Alias permutation from a hash of the opaque incident ID**, not a random draw (the owner asked for per-incident randomisation; a hash gives it without a seed slot). Aliases are plain (`svc-07`), never part-names like `svc-payment-masked`. Out-of-scope components aliased too (`dep-02`); operation and message words kept (§5.2).
2. **Up to 5 services per worker; Borda scores (6 − r)/5.**
3. **σ formula** as §5.4 (D/G shape); S2.5 calibrates it anyway.
4. **Digest cap about 2,000 tokens per worker.**
5. **Prompt-revision budget:** at most three revision rounds, judged on the dev part only, each round's HR@3 recorded in §10 (§5.8).
6. **Response cache across variants** (§5.6), replaying usage and wall time.
7. **The narrator moves to S2.8** (§5.5); S2.3 is 4 days, not 5.
8. **k = 0 is ABSTAINED**, not FAILED; FAILED is kept for an error outside the workers (e.g. a digest builder crash).
9. **Calls run sequentially** for determinism.
10. **Dev/held-out split by opaque-ID hash** (§5.8).

## 9. Left to the builder

Exact digest line wording; per-service line limits inside the cap; how tokens are counted for the cap; how the model digest is read from Ollama; where the cache lives (inside the store or a separate file, gitignored); how a window is recognised as RCAEval-format for L-f without adding a field to `TelemetryWindow`; the hang timeout value (today 120 s).

## 10. Results

(Filled after the build-data runs.)
