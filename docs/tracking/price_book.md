---
version: price-book-v1
currency: USD
as_of: "2026-10-26"
token_prompt_per_million: 0
token_completion_per_million: 0
cpu_per_vcpu_hour: 0.048
gpu_per_hour: 1.006
storage_per_gib_month: 0.023
storage_retention_months: 1
human_per_hour: 63.98
human_review_minutes: 15
opportunity_per_minute: 5600
ttcd_censor_s: 1800
---

# Price Book

**Purpose:** the coefficients that turn recorded usage into Cost per Resolution (CpR), the five-component cost defined in `docs/tracking/metric_contract.md` §3. The YAML block above is the single source: `helios/evaluation/cost.py` reads it and records its SHA-256 with every cost.

**Status:** price-book-v1 (S1.10, 2026-10-26, deviation entry 42). **Frozen at tag `build-freeze`** (S5.3); any change before then is a new deviation entry, none after.
**Owner:** researcher. Coefficients marked *assumption* are owner decisions to confirm before build-freeze.

---

## Coefficients

| Component | Coefficient | Value | Source |
|---|---|---|---|
| Token | per million prompt / completion tokens | 0 / 0 | The confirmatory runs use local inference (llama3.1:8b on Ollama, deviation entry 25). The metric contract records local token cost as zero; the tokens themselves are still counted (LLM gateway) and priced as GPU time below |
| Infrastructure — CPU | per vCPU-hour | 0.048 | AWS EC2 m5.large on-demand, us-east-1, Linux: 0.096 per hour for 2 vCPU ([Holori](https://calculator.holori.com/aws/ec2/m5.large/us-east-1), retrieved 2026-10-26) |
| Infrastructure — GPU | per GPU-hour | 1.006 | AWS EC2 g5.xlarge on-demand (one NVIDIA A10G, 24 GB — fits an 8B model), us-east-1 ([Holori](https://calculator.holori.com/aws/ec2/g5.xlarge/us-east-1), [DoiT](https://www.doit.com/compute/spot/us-east-1/g5.xlarge), retrieved 2026-10-26). Local inference is priced at its cloud-rental equivalent |
| Storage | per GiB-month | 0.023 | Amazon S3 Standard, first 50 TB, us-east-1 ([Cloudchipr](https://cloudchipr.com/blog/amazon-s3-pricing-explained), [Cloudian](https://cloudian.com/blog/5-components-of-aws-s3-storage-pricing/)) |
| Storage | retention, months | 1 | *Assumption:* incident telemetry kept for one month |
| Human time | per hour | 63.98 | U.S. BLS, software developers, median annual wage May 2024: 133,080 / 2,080 working hours ([BLS OOH](https://www.bls.gov/ooh/computer-and-information-technology/software-developers.htm)). Wage only, no overhead multiplier |
| Human time | review minutes per human-requesting verdict | 15 | *Assumption:* one engineer review of a PROVISIONAL verdict with a HITL request or a non-converged case; an automatic CONFIRMED verdict carries none |
| Opportunity | per minute of unresolved incident | 5,600 | The per-minute downtime figure the dissertation already uses (Ch2 financial-impact table, citing Chakraborty et al., 2024; commonly attributed to Gartner, 2014). See the caveat below |
| Opportunity | TTCD censoring, seconds | 1,800 | Metric contract §4: an incident with no correct published verdict is censored at Ch3's 30-minute incident window |

**Per-unit forms used by `cost.py`:** CPU 0.048 / 3,600 per vCPU-second; GPU 1.006 / 3,600 per GPU-second; storage 0.023 × 1 / 2^30 per byte; human 63.98 / 60 per minute.

## Caveats (for the chair call)

- **Opportunity cost dominates.** At 5,600 per minute a single censored incident costs 168,000, against cents of compute; Ch3 §3.8.4 anticipates this and reports components descriptively. A-H5 and B-H7 analyse log(CpR), so the coefficient scales every variant's opportunity cost alike, but the *ratio* of opportunity to compute decides how much algorithmic cost differences can show.
- **The 5,600 figure is weakly sourced.** It is widely attributed to a 2014 Gartner blog post rather than a study; later surveys give higher values (Ponemon 2016, about 9,000 per minute; EMA, 14,056 per minute, via [BigPanda's EMA eBook](https://start.bigpanda.io/rs/778-UNI-965/images/EMA_Outage_BigPanda_eBook.pdf)). It is kept for consistency with Ch2; a sensitivity analysis at the EMA value is proposed.
- **Cloud prices come from aggregators** that mirror the AWS price list; check them against aws.amazon.com before build-freeze.

## What each component measures

See `docs/tracking/metric_contract.md` §3 and `docs/sprints/s1-data-graph/s1_10_price_book_cost.md`.

| Component | Usage recorded | Where it comes from |
|---|---|---|
| Token | prompt and completion tokens of every model call, retries included | LLM gateway (`helios/pipelines/l_pipe/gateway.py`) → `PipelineVerdict.cost` |
| Infrastructure | HELIOS process CPU time per pipeline call; model compute time (server-side prompt evaluation + generation) as GPU time | Orchestrator (`_dispatch`) and LLM gateway |
| Storage | bytes of the incident's telemetry streams | `cost.window_bytes` |
| Human time | whether the published verdict requests a human | MAHC verdict state (S2) |
| Opportunity | time to correct diagnosis, censored at 1,800 s | TTCD (S2 / evidence runs) |
