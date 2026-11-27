# L6 larger-model subset and L7 judge models · design

**Date:** 2026-11-27 · **Status:** draft for owner approval · **Decisions:** L6 and L7 (lead-time register `docs/tracking/s0_11_lead_time_register.md`; owner "go L6 L7", 27 Nov; L6 model `llama3.1:70b`, owner choice) · **Streams:** E6 (S2-M11-EVAL04) and E5 (S2-M11-RES02)

## 1. What is decided

| Item | Decision | Registered as |
|---|---|---|
| **L6** | Run a 70B sensitivity subset locally with `llama3.1:70b` (4-bit, Ollama) | RB2 and D3 ("70B sensitivity if budget"), E6 |
| **L7** | One local judge model labels the E5 claims as a secondary reading beside the human raters; no paid API judge | E5 ("judges if budget"); A-H7 stays human-rated |

Both are exploratory. Neither changes a confirmatory hypothesis, test, metric, variant hash or the E1–E3 runs.

## 2. L6 · 70B sensitivity subset

### 2.1 Why a build change is needed

The frozen build pins the model: `helios/pipelines/l_pipe/lpipe_config.py` sets `MODEL_NAME = "llama3.1:8b"` and `EXPECTED_MODEL_DIGEST`, and the L-pipe raises `ModelMismatchError` when the served digest differs. The narrator uses the same `MODEL_NAME` (`helios/narrative/engine.py`). No frozen tool can run another model, and a changed checkout cannot read the pool or join `e_pool_bf5`, because the pool gate and `run` accept only the frozen build.

### 2.2 Design

**M-a · Sensitivity model setting.**
- `lpipe_config` gains one registered alternative: `SENSITIVITY_MODELS = {"l6": (name, digest)}`, with the digest of the downloaded `llama3.1:70b` fixed at download.
- A campaign planned with `--sensitivity-model l6` records the choice in `campaign.json`. Every run in it serves that model to the L-pipe workers and the narrator, checked by digest exactly as the 8B is.
- Without the option, nothing changes. There is no environment variable and no free model name: only a registered key can be chosen.

**M-b · Proof that the default is unchanged.** With the option absent, the new build reproduces the build-freeze-5 rehearsal stores on build data: the same rankings, states, narratives and cache keys. A test pins this.

**M-c · Freeze.**
- The change touches frozen paths, so it gets its own deviation entry, a new freeze record and tag `build-freeze-6`, and an entry recording the tag (the entry 110–111 pattern).
- E2, E3 and the 10% reruns keep running on build-freeze-5 from `e_pool_bf5`. They are finished before `../helios-e` moves to build-freeze-6, so every confirmatory run and its replication share one build.

**M-d · Subset.**
- The E6 rerun cases: every 10th case of the pool `case_order`, 24 cases. They are run with the five confirmatory variants that consult the model: HELIOS-Full, LLM-only, noConsensus, noRouter and noStructural. noLLM, D and G do not use it.
- That makes 120 runs, in one new campaign planned under build-freeze-6 with `--sensitivity-model l6`, phase `rerun` and the response cache bypassed.
- Seeds come from the same register (Protocol A: temperature zero, top-k one, the frozen seed).

**M-e · Reading.**
- Paired per case against the same variant's E1 run on the 8B: HR@1, HR@3, MRR, CpR and TTT.
- Reported as the mean difference with a BCa interval and as counts. There is no test, no Holm rank and no decision; the label is "model-size sensitivity (exploratory)".
- Scored with the frozen `score_runs.py` after E1–E3 are scored. The pool ground truth is read only through the pool gate.

**M-f · Compute.**
- Not yet measured. The pilot timed the 8B, 14B, 24B and 30B, not the 70B.
- Before planning the campaign, a pilot-style timing on 20 build worker prompts (`bin/pilot_model_timing.py` method, build data only) gives the wall time per call. That number, times the calls per run, sets the estimate, and the owner gives the go.
- The download is about 40 GB; free disk is about 400 GB.
- Runs only with the machine free, like E1–E3.

### 2.3 Risks

| Risk | Handling |
|---|---|
| The 70B is too slow locally | The timing in M-f comes before any campaign. If a run would take more than a night's share, cut the subset to Full and LLM-only (48 runs) by owner decision, or rent a GPU (RB2's original wording) |
| The 70B answers fail the worker parser more often | Parser acceptance is part of the M-f timing. Failures are counted and reported as the L-pipe failing, exactly as for the 8B, never retried with a different prompt |
| The frozen prompts were tuned on the 8B | Disclosed. The sensitivity measures what the frozen product gains from a larger model with the same prompts, not the best possible 70B system |

## 3. L7 · Local judge model

### 3.1 Design

**J-a · Judge.** `devstral:24b`, local and already downloaded. It is neither the narrator's family (Llama) nor the L6 model. In the S5.3 pilot it answered all 20 worker prompts within the parser. A paid API judge is not funded; adding one later needs its own entry.

**J-b · Task.**
- For every displayed claim in the E5 labelling set (the 480 Full and noLLM pool narratives), the judge gives the label the raters give under the frozen rubric (entry 102, rubric `f705edb8`).
- It sees exactly what a rater sees: the claim and its displayed evidence, blind to variant (the labelling set's masking).
- It never sees pool ground truth, rater labels or other claims' labels.

**J-c · Prompt and decoding.**
- The judge prompt is written and checked on build narratives only: the S2.9 planted known-corrupted claims and the training set.
- Its SHA-256 is fixed in the deviation entry before the judge reads any pool claim.
- Protocol A decoding: temperature zero, top-k one, a seed from the register.

**J-d · Order.** The judge runs after the human labels and the adjudication are complete. The prompt is frozen before then (J-c), so neither side can be tuned to the other.

**J-e · Reading.**
- Cohen's κ between the judge and the adjudicated human label, overall and per label.
- H_fact from the judge's labels beside the human H_fact.
- All labelled "secondary, exploratory". A-H7's result is the human reading only. If E5 is incomplete by 31 March, A-H7 is reported as incomplete (entry 102), and the judge reading never stands in for it.

**J-f · Tool.** `scripts/judge_claims.py`, outside the frozen paths. It reads the labelling set and writes judge labels with input digests (the labelling set, prompt SHA and model digest) to a separate signed file. It prints counts only and needs no freeze.

**J-g · Compute.** About 1,000 prompt tokens per claim (S5.3 §5.4). The per-claim time comes from a 20-claim timing on build narratives before the pool run. Runs only with the machine free.

## 4. Entries

| Entry | Content | When |
|---|---|---|
| Next (L6) | M-a to M-f: the 70B sensitivity subset and the sensitivity-model setting. The change touches frozen paths, so a new freeze record follows | Before the code change |
| Next + 1 (L7) | J-a to J-g; the judge prompt SHA is added when the prompt is frozen, by a further entry if the first one cannot name it | Before the judge reads any pool claim |
| Later | Tag `build-freeze-6` recorded (entry 111 pattern) | After the freeze PR merges |

## 5. Order of work

1. Owner approves this note, then the L6 and L7 entry texts ("approve N" each).
2. Time the 70B (M-f) and the judge (J-g) on build data only, with the machine free.
3. Build M-a and M-b on `main`, plus the freeze record, then tag `build-freeze-6` with the owner's OK. This happens after the 10% reruns, or on `main` in parallel, without moving `../helios-e` until then.
4. Run the L6 campaign on the owner's go.
5. Build the judge tool (J-f) and freeze its prompt (J-c). Run it after E5 adjudication.
