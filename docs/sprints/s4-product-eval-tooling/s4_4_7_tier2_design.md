# S4.4–S4.7 Tier 2: design

**Rows:** S2-M9-ENG04 (PII redaction), ENG05 (shadow and recommendation modes), ENG06 (FGSV lite), ENG07 (IOL lite) · **Effort:** ½ + ½ + 1 + ½ days · **Depends on:** S4.1 (API), S4.2 (console) · **Status:** approved 2026-11-14 (T-a to T-k as recommended)

## 1. What is fixed already

- **Task** (`helios_task_breakdown.md` S4.4–S4.7):
  - pattern-based redaction before any LLM call;
  - modes that never write to production;
  - a KS gate plus replay on recorded data, with PASS / FAIL / STALE;
  - HELIOS self-telemetry in the graph under `tenant=self` (basic).
- **Done when:** each is behind its flag with tests, or recorded as moved to Stage B.
- **Owner decision 2026-11-11** (S4 plan): build all four in S4.
  - S4.4 and S4.5 are product settings outside the VCL manifest (option a). Variant hashes and `variants.py` stay unchanged, so the VCL is not re-frozen.
  - S4.6 and S4.7 go behind their existing flags, `fgsv_ks_gate` and `iol_self_telemetry`. Both are ON in HELIOS-Full.
- **S4 plan constraints:**
  - redaction is OFF in evidence runs, with a check on build data of what it would change;
  - evidence runs use recommendation mode;
  - Full's verdicts on build data stay byte-identical with `iol_self_telemetry` ON and OFF.
- **Module flags:** the new modules follow the repository's convention for module markers, as `HELIOS_ENABLE_CONSOLE` does for the API.
  - S4.4 and S4.5 add `HELIOS_ENABLE_PII_REDACTION` and `HELIOS_ENABLE_ACTIONS`.
  - The FGSV and IOL code is also gated at run time by `VCLFlag.FGSV_KS_GATE` and `VCLFlag.IOL_SELF_TELEMETRY`, read from the run's manifest.
- **Chapter 3:**
  - Algorithm 4 (FGSV): a two-sample KS test on pillar-matched samples with α_ks = 0.05. A gate failure gives STALE. When the gate passes, the action runs in the twin under an ASRE mode (structural, WAL replay or sketch). Exceeding the blast radius gives FAIL.
  - C5 (IOL): self-telemetry written to the same L1 graph under `tenant=self` and read by the same detection apparatus, with no separate monitoring stack.
  - Privacy Gateway: pattern-based PII detection plus NER, with deterministic placeholders that keep sentences readable for the LLM.
  - E-H4: the false-accept rate of invalid actions under a fidelity-break perturbation.
  - E-H6: degradation-detection latency under injected control-plane degradation.
  - Both are exploratory.
- **Stage B keeps the full versions:**
  - B2: the full Privacy Gateway (NER, per-tenant differential privacy);
  - B3: the full twin, ASRE WAL replay and sketch modes, remediation templates, automatic actions under α;
  - B4: full IOL.

## 2. What exists today

| Piece | State |
|---|---|
| LLM calls | Two callers, the L-pipe workers (`workers.py`) and the narrator (`narrative/llm.py`). Both go through `LLMGateway.generate` and build their response-cache key from the prompt text *before* the gateway |
| Actions | None. HELIOS publishes verdicts; the API records human decisions (S4.1, S4.2). There is no remediation proposal, no actuator and no L4 code |
| `fgsv_ks_gate`, `iol_self_telemetry` | In the registry and the variants, read by nothing. `catalog.unconsumed_variants` therefore keeps HELIOS-noFGSV and HELIOS-noIOL out of the phase-E schedule |
| `tenant` | On every UEG-C node, default `prod`. Agent reasoning steps are already `self`. `candidate_ids()` and both pruners rank and prune only `prod` services |
| Snapshot identity | `snapshot_hash` is the capture's `window_hash`, not a hash of the graph. Nodes added to the graph do not change it |
| Detector | The frozen trigger detector (`telemetry/trigger.py`: buckets, threshold, persistence; S2-M7-EVAL01) |
| scipy | Already a main dependency (two-sample KS) |
| Self-telemetry already measured | Per-pipe wall times (`ran_ms`), gateway token and compute usage, cache hits, model errors, narrator fallbacks, H_struct counts, gate outcome |

## 3. Decisions for the owner

### T-a. Order and packaging

- **Recommended:**
  - one branch and one PR, four commits (one per task) plus tracker commits;
  - order S4.6 → S4.5 → S4.7 → S4.4, because S4.5's modes govern the action proposals S4.6 creates.
- **Alternative:** four PRs. They are small, so review cost would roughly double for little gain.

### T-b. S4.4 PII redaction: where and what

- **Recommended:**
  - **Where:** one module, `helios/privacy/redact.py`, called inside `LLMGateway.generate` and `replay`. That is the only path to the model, so nothing reaches it unredacted.
  - **Cache:** when redaction is ON, the cache key also covers the ruleset id, so redacted and raw answers never share a key. With redaction OFF, every key is byte-for-byte unchanged, so the evidence cache stays valid.
  - **Rules:** email; IPv4 and IPv6; MAC address; card numbers (Luhn-checked, so random digit runs are left alone); phone numbers in international form; JWTs and `Bearer` tokens; key–value secrets (`password=`, `token=`, `api_key=`, `secret=`); AWS access-key ids.
  - **Placeholders:** deterministic and numbered by first appearance within one prompt (`<EMAIL_1>`, `<IP_2>`), so the same value always gets the same placeholder and sentences stay readable.
  - **Never redacted:** the incident's service names, evidence ids and metric names, so citations and rankings mean the same with redaction ON. Trace and span ids are not PII and are left alone.
  - **Record:** counts per rule go into the gateway usage and the CoE entry, never the values.
- **Left for Stage B (B2):** NER-based redaction of names in free text, redacting stored evidence, and differential privacy.

### T-c. S4.4 setting and the build-data check

- **Recommended:**
  - **Setting:** `HELIOS_PII_REDACTION=off|on`, read at run start and stamped in the run record. Default `off`; the compose file sets `on` for product use (`deploy/.env.example`).
  - **Evidence runs:** OFF, as the owner decided. The campaign refuses `on` for a confirmatory phase, so it cannot be switched on by accident.
  - **Check:** `bin/pii_scan.py` runs the redactor over every text that reaches a prompt on **build data only** (OTel captures and the RCAEval build split; the pool stays locked). It reports hits per rule and per dataset, with no values.
  - **Expectation:** RCAEval logs probably hold pod IP addresses, so redaction is unlikely to be a no-op. The scan records what ON would change, and §7 reports it.

### T-d. S4.5 shadow and recommendation modes

- **Recommended:**
  - **Setting:** `HELIOS_ACTION_MODE=recommend|shadow`, default `recommend`. There is **no** automatic mode. The parser refuses `auto` with "Stage B: needs α and the full twin".
  - **recommend:** verdicts and action proposals (T-e) are shown to responders as recommendations. A person acts outside HELIOS, and an accept in the console records "recommendation accepted". Evidence runs use this mode.
  - **shadow:** HELIOS runs and records everything, but responders don't see the result while the incident is open, so it can't influence them.
    - `reader` and `reviewer` keys get the verdict and its proposal only after the incident has a decision from a key other than HELIOS's own.
    - `admin` keys always see it.
    - The console shows "Shadow mode: recorded for comparison only".
    - The ledger keeps HELIOS's would-be answer and its time, for a later comparison with the human answer.
  - **"Never writes to production" is structural:** Stage A has no actuator. `helios/actions/` defines an `Actuator` protocol whose only implementation is `NoActuator`, which raises if called.
  - **Tests:**
    - the action path opens no socket and starts no process (both are monkeypatched to fail);
    - no module outside the tests imports an actuator other than `NoActuator`.
- **Stage B (B3):** a real actuator, gated by FGSV, HITL and α.

### T-e. S4.6 FGSV lite: proposal, twin, gate, replay

- **Recommended:**
  - **Proposal:** one per stored run, built from the fused top-1 service.
    - Action kinds in the lite version: `restart` (stateless service) and `scale-out`. Stateful services (databases, Kafka, Redis) get `escalate-to-human`, which FGSV never passes.
    - The kind comes from the service's known role in the topology, not from the LLM.
    - Remediation templates are Stage B (B3).
  - **Twin on recorded data:** the capture's normal period before the trigger is split in two.
    - The **twin** sample is the earlier half: the twin was built from older telemetry.
    - The **production** sample is the half just before the trigger.
    - This tests whether the twin still resembles production, as Algorithm 4 intends, using only recorded data.
  - **KS gate (Algorithm 4):**
    - samples are pillar-matched: metrics per series, logs as per-bucket counts per template, traces as span durations;
    - only the action's target and its blast-radius services are tested, because fidelity matters where the action lands;
    - two-sample KS per series, Holm-adjusted within each pillar;
    - the gate fails if any pillar rejects at α_ks = 0.05 (Ch3's value).
    - **Failure → STALE**, with a reason: `ks_gate`, `no_twin_data` (a normal period too short for both halves), or `no_structure` (replay cannot run without trace edges).
  - **Replay, ASRE structural mode** (Ch3 names it as one of the three modes):
    - Over the incident graph's structural edges, replay asks two questions:
      - does the action's target reach (downstream along call edges) the services the D-pipe scored anomalous? That is **coverage**;
      - how many services call the target and would feel a restart? That is the **blast radius**.
    - **PASS** when coverage reaches a set share and the blast radius is within a set budget. Otherwise **FAIL**, with the reason.
  - **Record:** a new CoE step `A`, holding the proposal, the KS p-values per pillar, coverage, blast radius, verdict and reason.
    - It is added after the fused verdict and after the publication time that TTT and TTCD read, so neither moves.
    - The ranking, confidence and narrative are unchanged. A test checks the ranked lists match with the flag ON and OFF.
  - **noFGSV:** no step `A` validation. The proposal is recorded as `UNVALIDATED`, the state in which Ch3 says it would go to HITL directly.
- **Parameters to freeze:** the coverage share and the blast-radius budget.
  - They are set on build data (OTel plus the RCAEval build split): the values with the fewest PASS verdicts on wrong targets while correct targets keep passing, with the curve reported.
  - They are then frozen in `helios/actions/fgsv_params.json` with a hash in the CoE parameter hashes, as for the other frozen parameters.
  - The pool is never read for this.

### T-f. S4.6 E-H4 perturbation protocol

- **Recommended:**
  - a campaign option `--fgsv-perturb shift=k` for exploratory runs only (the campaign refuses it in confirmatory phases). It shifts every twin series by *k* standard deviations of its own production half: a fidelity break;
  - *k* and the share of perturbed incidents are frozen with T-e's parameters;
  - **E-H4 metric:** an *invalid action* is one whose target is not the labelled root cause. A *false accept* is PASS on an invalid action (noFGSV: `UNVALIDATED` counts as accepted, as Ch3 has it). Scoring reads labels only where scoring already does (build data now, the pool after `build-freeze`).
- **Honest limit, for §7 and Chapter 4:** under the fidelity break, FGSV gives STALE by construction, so E-H4's perturbed contrast mostly checks that the gate fires. The informative number is the **unperturbed** false-accept rate, where only replay separates correct from wrong targets; it is reported beside E-H4.

### T-g. S4.7 IOL lite: what goes into the graph, and how it is read

- **Recommended:**
  - **Self-telemetry:** one record per run, `helios/telemetry/self_telemetry.py`. It holds per-pipe wall times, model compute ms and tokens, cache hits, model errors and timeouts, narrator fallbacks, the gate outcome and non-convergence. Nearly all of this is already measured.
  - **In the graph:**
    - `incident_graph` adds control-plane nodes under `tenant=self`: `helios.dpipe`, `helios.gpipe`, `helios.lpipe`, `helios.model`, `helios.narrator`, `helios.consensus`;
    - structural edges between them (`lpipe → model`, and so on);
    - each node carries the series of its metrics over the **previous** runs of the campaign. A run's own telemetry is not known when its graph is built.
    - The existing agent-reasoning-step nodes link to `helios.lpipe`, so a path from a production service through a reasoning step to a degraded control-plane node is a single graph query (Ch3 query type (i)).
  - **Read by the same detector:** the frozen trigger detector's firing rule (`decide`: buckets, threshold, persistence) runs over the self partition's series, with the run index as the bucket. This is the "same apparatus" claim, with no separate threshold to tune.
    - The output is a CoE step `S`: which component is degraded and from which run.
    - The API and console show "HELIOS control plane degraded" on that verdict.
  - **Byte-identical rule:**
    - self nodes are never candidates (`candidate_ids()` is `prod` only, and so are both pruners and the G-pipe rankers);
    - the narrator never receives self nodes.
    - **Test:** run Full on the OTel build campaign with the flag ON and OFF, cache warm; verdict rows, fused rows and narratives must match byte for byte. Step `S` exists only with the flag ON.
- **Stage B (B4):** live OTLP self-instrumentation of the collector and exporter, cross-tenant economic queries, and the full IOL.

### T-h. S4.7 E-H6 injection protocol

- **Recommended:** **synthetic injection into the self-telemetry record** (`--iol-inject component=model,from=run_k,factor=f`). From run *k* on, the recorded model compute time is multiplied by *f*, and optionally an error rate is added.
  - It is deterministic, costs nothing, and cannot change a verdict, because only the measurement changes.
  - **E-H6 metric:** detection latency, in runs and in seconds of campaign time, from the injection to step `S` first naming the component.
  - noIOL never detects it, so its latency is censored at campaign end and reported as "not detected".
  - *k*, *f* and the error rate are frozen with T-g.
- **Alternative:** a real delay in the model gateway. It is more realistic, but timeouts would then change verdicts, and it costs compute. **Left for Stage B.**

### T-i. Deviation entry and pre-registration

- **Recommended:** **one** entry, its text approved by you before it is appended, covering S4.6 and S4.7 as Stage A lite operationalisations of E-H4 and E-H6:
  - FGSV: a recorded-data twin, structural ASRE only, the coverage and blast-radius parameters, the perturbation protocol;
  - IOL: self-telemetry from previous runs, read by the frozen trigger rule, synthetic injection.
  - Both stay exploratory. No confirmatory test changes.
  - The frozen values also go in the OSF addendum draft. `metric_contract.md` is not edited.
- **No entry for S4.4 and S4.5:** they are outside the manifest, OFF or without effect in evidence runs, and change no hash.

### T-j. Schedule and catalog

- **Recommended:**
  - once `fgsv_ks_gate` and `iol_self_telemetry` have readers, `unconsumed_variants` stops refusing HELIOS-noFGSV and HELIOS-noIOL by itself, so phase E includes them;
  - a test pins that, and that noCogni and HIS3 are still refused;
  - the S4 plan's RES01 note (noFGSV and noIOL "run only if S4.6 and S4.7 are built") is updated.

### T-k. Verification

- **Recommended:**
  - **Unit tests:** each redaction rule (hits, near misses, never-redacted names, placeholder numbering, cache-key behaviour OFF and ON); modes (refusal of `auto`, shadow visibility per role, no socket or process from the action path); KS gate (synthetic samples that pass and fail, too-short periods, Holm); replay (coverage and blast radius on small graphs); IOL (self nodes never ranked, detector on an injected series).
  - **Build-data walk-through:**
    - `pii_scan` over the build data;
    - the FGSV verdict counts on the OTel campaign and the RCAEval build split, with the false-accept rate perturbed and unperturbed;
    - the IOL byte-identical check, then a run with injection, showing the detection latency;
    - a shadow-mode check through the API (an ops key can't see the verdict before a decision, an admin key can).
  - **Gate:** the full pre-push gate plus the console tests. Results go in §7.

## 4. Out of scope

- Real actuation and automatic actions (Stage B3).
- The full twin with traffic mirroring, ASRE WAL replay and sketch modes (B3).
- NER-based redaction, redacting stored evidence, differential privacy (B2).
- Live OTLP self-instrumentation and the full IOL (B4).
- Any change to `variants.py`, `analysis_plan.py` or the metric contract.
- Any read of pool data or labels.

## 5. Risks

| Risk | Mitigation |
|---|---|
| The KS gate rejects often on clean recorded data (autocorrelation, slow drift), so most verdicts are STALE | §7 measures the STALE share on build data first. If it is high, I report it and ask you before anything is frozen; it is not tuned away silently |
| RCAEval build cases lack trace edges, so replay gives STALE `no_structure` for most of them | Reported per dataset; E-H4 scoring reports such cases separately, as Ch3 asks for `shadow_suspended` cases |
| A self node leaks into ranking or the narrative | The byte-identical test (T-g) runs in CI on fixtures and once on the OTel build campaign |
| Redaction changes a service name or evidence id | Never-redact list plus a test over every build-data service name |

## 6. Effort

About 2½ days, as planned (½ + ½ + 1 + ½), plus the walk-through.

## 7. Results

Implementation 2026-11-14 on branch `s4/tier2`. Aggregates (no case IDs, no labels) are in `calibration/`: `fgsv_calibration.json`, `tier2_walkthrough.json`, `iol_eh6_sweep.json`, `pii_scan.json`.

### 7.1 What was built

| Task | Code | Flag or setting |
|---|---|---|
| S4.6 FGSV lite | `helios/actions/fgsv.py`; CoE step `A`; `bin/fgsv_calibrate.py`; frozen `data/frozen/fgsv_params.json` | `VCLFlag.FGSV_KS_GATE` (noFGSV records `UNVALIDATED`) |
| S4.5 Modes | `helios/actions/modes.py`; API shadow visibility; console recommendation line | `HELIOS_ACTION_MODE=recommend\|shadow` (no automatic mode) |
| S4.7 IOL lite | `helios/telemetry/self_telemetry.py`; CoE step `S`; `bin/iol_sweep.py`; frozen `data/frozen/iol_injection.json` | `VCLFlag.IOL_SELF_TELEMETRY` |
| S4.4 Redaction | `helios/privacy/redact.py` in `LLMGateway.generate`; cache key namespaced when on; `bin/pii_scan.py` | `HELIOS_PII_REDACTION=off\|on` (confirmatory runs refuse `on`) |

- **API v1.2** (additive): `Verdict.action` (kind, target, mode, FGSV verdict, reason) and `Verdict.control_plane_degraded`, both null for blind keys. Shadow runs return 404 to reader and reviewer keys until a decision exists on their incident; admin keys always see them.
- **Campaign:** `plan --fgsv-perturb` (E-H4) and `plan --iol-inject SPEC` (E-H6) are stored in the campaign config only when set, refused for the pool, and the injection must be on the frozen ladder. Each variant keeps its self-telemetry in `self/<stem>.<variant>.jsonl`, so a resumed campaign keeps its history.
- **Compose:** the runner passes both product settings through with the evidence defaults (`off`, `recommend`); `deploy/README.md` documents them.
- **Schedule (T-j):** both flags now have readers, so phase E includes HELIOS-noFGSV and HELIOS-noIOL; only noCogni and HIS3 stay refused (test pinned).

### 7.2 Departures from §3, and why

1. **KS gate pools per pillar** (T-e said per series, Holm within the pillar). The build windows have 3–5 one-minute buckets per half: per-series tests have almost no power, and the Holm correction over many series removes the rest. Each series is scaled by its production half (median, MAD) and pooled, one test per pillar at a 15-second sampling interval, Holm across pillars. Traces enter through the OTel span metrics in P1; there is no separate trace pillar.
2. **The pipelines rank on the production graph only.** The self partition is composed onto the incident graph for step `S` (`with_self_partition`), not passed into D/G/L. That is the strongest form of the byte-identical rule; the partition and the cross-tenant query are still one UEG-C object.
3. **Frozen files live in `data/frozen/`** (the repository's convention), not `helios/actions/`.
4. **Compose defaults redaction to `off`**, not `on` (T-c): confirmatory runs refuse `on`, so a default of `on` would block the pool campaign in compose. Operators set it for production telemetry.
5. **The perturbation is a flag** (`fgsv_perturb`) applying the frozen `perturb_shift`, not a free `shift=k`; a no-op for noFGSV.

### 7.3 FGSV lite

**KS gate on clean build data** (owner decision 2026-11-14, after the risk in §5 materialised). Over every in-scope service of the 63 OTel build graphs (1,260 targets), the gate marks **52%** STALE. Metrics cause it (median KS distance 0.19 between the halves, above Ch3's d = 0.3 equivalent of about 0.12); logs reject at the nominal rate (6%). The v3 captures vary load in the normal period by design (entry 50), so the twin really is stale. An effect-size gate would still mark 56%, per-series Holm 75%. **Kept as Chapter 3 has it**; STALE stays a first-class covariate.

**Replay parameters** (Youden's J over targets that clear the gate and are actionable; ties to the stricter setting): coverage ≥ 0.75, at most 3 direct callers. Correct targets pass 84% (26 of 31), wrong targets 36% (175 of 484). RCAEval build cases have no trace edges (0 of 495 with structure): every one is STALE `no_structure`. The fidelity break chosen for E-H4 is one production-half spread (k = 1): the gate catches it on 97.6% of targets (k = 2: 99.6%).

**On HELIOS-Full's own top-1** (63 runs, cache only):

| Arm | PASS | FAIL | STALE | UNVALIDATED | Wrong targets accepted | Correct targets accepted |
|---|---|---|---|---|---|---|
| Full | 24 | 10 (coverage) | 29 (`ks_gate`) | — | 12 of 32 (37.5%) | 12 of 31 (38.7%) |
| noFGSV | — | — | — | 63 | 32 of 32 | 31 of 31 |
| Full, fidelity break | — | — | 63 (`ks_gate`) | — | 0 of 32 | 0 of 31 |

- 52 proposals are `restart`, 11 `scale-out`; no top-1 was stateful.
- **Honest reading for E-H4 and Chapter 4:** FGSV's lower false-accept rate comes almost entirely from the gate (STALE), not from replay. Among proposals that clear the gate, replay passes 12 of 17 wrong targets and 12 of 17 correct ones: it does not separate HELIOS's own mistakes, which tend to be upstream callers that cover the anomalous services as well as the true root cause does. The all-candidate calibration (J = 0.48) overstates replay's value on the targets HELIOS actually proposes. E-H4 is reported with this split; the perturbed contrast only shows that the gate fires.

### 7.4 IOL lite

- **Byte-identical rule:** Full against noIOL on the 63 OTel build cases: all 189 verdict rows, 63 fused rows and 63 narratives are identical (decision content; run IDs, config hashes and wall time excluded). Full has step `S` on every run, noIOL on none; no run of the clean campaign was flagged degraded.
- The same holds for Full against noFGSV (step `A` is the only difference).
- **E-H6 severity ladder** (owner decision 2026-11-14): the frozen rule (z ≥ 10 for 3 runs) flags a model slowdown injected at run 30 of the recorded history:

| Factor | ×2 | ×3 | ×5 | ×8 |
|---|---|---|---|---|
| Detected (latency in runs) | no | no | yes (3) | yes (3) |

  A clean history is never flagged. Three runs is the shortest the persistence rule allows. Per-run timings vary about 40% between incidents, which is why ×2 and ×3 stay below the threshold; injected from run 20 (less history), ×5 is missed and ×8 takes 5 runs. The ladder is frozen in `data/frozen/iol_injection.json`; phase E runs one exploratory campaign per factor and reports detection rate and latency per factor, noIOL never detecting.
- The first E-H6 attempt (×3, a single factor) found nothing, which is what led to the ladder question; it is reported, not hidden.

### 7.5 PII redaction

- **Build-data check (T-c):** redaction changes **no** prompt. Over every L-pipe worker prompt of the build data (otel_build_v3: 189 prompts from 63 cases; rcaeval_build: 615 from 495), no rule matches. Turning redaction on would therefore change nothing on build prompts.
- **Why:** the raw log lines do contain such values. OTel: 687,072 IP addresses, 7,937 email-shaped strings and 77 card-like numbers, in all 63 cases. RCAEval: 115,881 IPs, 332,185 emails and 8,554 card-like numbers, in 120 of 495 cases. The digests template every log line (variable parts become `<*>`) and replace service names with aliases before a prompt is built, so none of it reaches the model. Redaction is the guard for any future digest or narrator input that carries raw text.
- **Card rule:** the first scan, with Luhn alone, matched 2,741 and 35,440 numbers in raw logs (long numeric ids). Requiring a card-scheme prefix cut that to 77 and 8,554. `RULES_VERSION` is part of the ruleset id, so a change to a rule's check changes the id and the cache namespace.
- **Evidence runs** keep redaction off (confirmatory runs refuse it); with it off, every response-cache key is the pre-S4.4 key (test).
- The narrator's inputs are CoE evidence items built from the same digests; the scan covers the L-pipe prompts only.

### 7.6 Verification

- **New tests:** FGSV (`tests/actions/test_fgsv.py`, 14), modes and the no-actuator scan (`tests/actions/test_modes.py`), redaction rules, near misses, cache keys and gateway (`tests/test_redact.py`), self-telemetry and the frozen ladder (`tests/test_self_telemetry.py`), runner equivalence for noIOL and noFGSV plus the confirmatory refusals (`tests/test_runner_tier2.py`, 8), API v1.2 and shadow visibility (`tests/api/test_api_tier2.py`, 5), compose defaults, the refused-variant pin, and one console test (16 in all).
- **Full pre-push gate** (with pipefail) passed on the final tree: ruff, ruff format, black, mypy, pytest (coverage 96.48%), `verify_ledgers`, `verify-public` (88 entries), `verify_captures`, `verify_osf_freeze --verify`, `validate-tracking`, the ablation notebook, and `node --test tests/console/`.
- **Walk-through:** HELIOS-Full, noIOL, noFGSV, Full with the fidelity break, and Full with self-telemetry recorded, each over the 63 otel_build_v3 cases from the response cache (no model calls). The comparison was done with scratch scripts; their aggregates are in `tier2_walkthrough.json`, and the E-H6 ladder is reproducible with `bin/iol_sweep.py`.
- **Packaging:** one feature commit instead of the four T-a proposed. The runner and the API carry all four tasks in the same functions, so a split would have been artificial; the table in §7.1 maps each task to its files.
- **Pool:** never read. Calibration and scans use `otel_build_v3` and `rcaeval_build` only.
