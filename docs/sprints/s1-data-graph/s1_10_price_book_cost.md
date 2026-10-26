# S1.10 — Price book, token accounting, cost · design note

**Task:** S1.10 (tracking S2-M6-ENG08) · **Date:** 2026-10-26 · **Code:** `helios/pipelines/l_pipe/gateway.py` (LLM gateway), `helios/evaluation/cost.py` (CpR), `docs/tracking/price_book.md` (price-book-v2) · **Deviation:** entries 42 (price-book values) and 43 (cloud provider profiles) · **Flags:** cost is computed after dispatch for every variant; the gateway sits inside the L-pipe (`l2c_llm`)

## Chapter 3 and the contract

CpR is "the five-component sum of token cost, infrastructure cost, storage cost, human-minute cost, and opportunity cost, computed per incident under the pre-registered price book" (§3.8.4, p. 146); "the Plane 3 LLM Gateway token counter will provide per-episode token spend … and the Plane 7 Critic Agent post-incident computation module will aggregate" the five components (p. 130). Metric contract §3 fixes what each component measures; this task supplies the meter, the coefficients and the computation.

## Token accounting — the LLM gateway

`LLMGateway` wraps the model client; every call of an episode passes through it, so **retries are counted** (before S1.10 only the accepted answer's tokens were kept, and none when every answer failed validation). A call that fails before the model answers counts as a failed call with no tokens. The gateway also records **model compute time**, Ollama's `prompt_eval_duration + eval_duration`, as the episode's GPU time (`PipelineVerdict.cost.gpu_ms`). The orchestrator's CPU time covers only the HELIOS process, so the two never overlap. The L-pipe output also reports `llm_calls` and `llm_failed_calls`.

## Cost — `helios/evaluation/cost.py`

| Component | Formula |
|---|---|
| Token | prompt tokens × prompt price + completion tokens × completion price, per million |
| Infrastructure | CPU seconds × vCPU-hour price / 3,600 + GPU seconds × GPU-hour price / 3,600 |
| Storage | telemetry bytes / 2^30 × GiB-month price × retention months |
| Human time | review minutes × hourly rate / 60 when the published verdict requests a human, else 0 |
| Opportunity | TTCD minutes × per-minute cost; no correct verdict (or TTCD ≥ 1,800 s) is censored at 1,800 s |

`load_price_book()` reads the YAML front matter of `price_book.md` (single source, every field required, none negative) and keeps its SHA-256; each `CostBreakdown` carries the price-book version and digest, plus `total` and `log_total` (the analysed form). `incident_usage()` sums one run's verdict usage; `window_bytes()` measures the incident's telemetry streams. A run with no CPU or GPU time is refused (the contract: infrastructure time is never zero, so zero means usage was not recorded).

## Price book (values and sources in `docs/tracking/price_book.md`)

USD. Shared coefficients:

| Coefficient | Value |
|---|---|
| Tokens | 0 (local inference; tokens still counted, their model time priced as GPU time) |
| Storage retention | 1 month (*assumption*) |
| Human time | 63.98 per hour (BLS median, software developers, May 2024) |
| Review time | 15 minutes per human-requesting verdict (*assumption*) |
| Opportunity cost | 5,600 per minute (the figure Ch2 already uses) |
| Censoring | 1,800 s |

**Cloud profiles (price-book-v2, owner request 2026-10-26).** Infrastructure and storage are priced from one named machine per provider, with service, machine type, region, terms, source and a `verified` flag, so the owner can replace each value from the provider's own price list:

| Provider | Role | Region | CPU | GPU | Storage |
|---|---|---|---|---|---|
| AWS | primary | us-east-1 | EC2 `m5.large`, 0.096/h for 2 vCPU | EC2 `g5.xlarge`, A10G, 1.006/h | S3 Standard, 0.023 |
| GCP | sensitivity | us-central1 | `n2-standard-2`, 0.0971/h | `g2-standard-4`, L4, 0.7068/h | Cloud Storage Standard, 0.020 |
| Azure | sensitivity | eastus | `Standard_D2s_v5`, 0.096/h | `Standard_NC4as_T4_v3`, T4, 0.526/h | Blob Hot LRS, 0.0208 |

Both AWS EC2 prices were checked against AWS's public price data (`ec2-ondemand-without-sec-sel`, US East N. Virginia, Linux, published 2026-10-23); everything else is from third-party trackers, marked `verified: false`. `load_price_book(provider=...)` returns one profile (the primary by default) and `load_price_books()` returns all; each `CostBreakdown` names its provider. The GPUs differ (A10G, L4, T4), so per-hour GPU prices are not like-for-like. Per-token pricing from a throughput benchmark on each reference GPU is an open point.

**For the chair call:**
- Opportunity cost dominates CpR by orders of magnitude.
- The 5,600 figure is weakly sourced; a sensitivity analysis at EMA's 14,056 per minute is proposed.
- The two *assumptions* (retention, review minutes) are owner decisions to confirm before build-freeze.
- Provider choice moves mainly the compute components, so a compute-only CpR is worth reporting descriptively.

## Done-when

Hand-computed cost matches on a fixture (`tests/evaluation/test_cost.py`):
- every component worked by hand under a round-number price book (total 195.032), plus the automatic, censored and refused cases;
- one incident under the frozen book's AWS profile (total 22,416.0674067) and under the GCP and Azure profiles.

Retry metering is tested in `tests/pipelines/test_lpipe_gateway.py`: two attempts give 200 + 50 tokens and 750 ms of model time. GPU time reaching the result row is tested in `tests/test_orchestrator_runner.py`.

## Open points

- **Human time and TTCD inputs** come from MAHC's verdict state and the published-verdict timeline (S2 and the evidence runs). `cpr()` takes them as arguments until then, and costs are not yet stored in a table. `ConsensusVerdict.cpr` stays `CPR_PENDING` until the fused verdict exists.
- **Server-side CPU** (Ollama's own process) is not metered beyond model compute time.
- **Price book freezing.** The price book is frozen at tag `build-freeze`. Its digest goes into the build-freeze record and the reproducibility manifest (S5.3).
