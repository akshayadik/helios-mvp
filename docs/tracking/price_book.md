---
version: price-book-v2
currency: USD
as_of: "2026-10-26"
primary_provider: aws
token_prompt_per_million: 0
token_completion_per_million: 0
storage_retention_months: 1
human_per_hour: 63.98
human_review_minutes: 15
opportunity_per_minute: 5600
ttcd_censor_s: 1800
providers:
  aws:
    region: us-east-1 (US East, N. Virginia)
    cpu:
      service: Amazon EC2
      machine_type: m5.large
      vcpus: 2
      terms: on-demand, Linux, shared tenancy
      price_per_hour: 0.096
      verified: true
      source: AWS public EC2 price data (ec2-ondemand-without-sec-sel, US East N. Virginia, Linux), published 2026-10-23
    gpu:
      service: Amazon EC2
      machine_type: g5.xlarge
      accelerator: 1x NVIDIA A10G 24 GB
      terms: on-demand, Linux, shared tenancy
      price_per_hour: 1.006
      verified: true
      source: AWS public EC2 price data (ec2-ondemand-without-sec-sel, US East N. Virginia, Linux), published 2026-10-23
    storage:
      service: Amazon S3
      tier: S3 Standard, first 50 TB per month
      price_per_gib_month: 0.023
      verified: false
      source: third-party guides (Cloudchipr, Cloudian), retrieved 2026-10-26
  gcp:
    region: us-central1 (Iowa)
    cpu:
      service: Google Compute Engine
      machine_type: n2-standard-2
      vcpus: 2
      terms: on-demand, Linux, no committed-use or sustained-use discount
      price_per_hour: 0.0971
      verified: false
      source: third-party trackers (Holori, DevZero), retrieved 2026-10-26; SpendArk lists 0.0777
    gpu:
      service: Google Compute Engine
      machine_type: g2-standard-4
      accelerator: 1x NVIDIA L4 24 GB
      terms: on-demand, Linux
      price_per_hour: 0.7068
      verified: false
      source: Google accelerator-optimized pricing page (region not shown) and Holori, retrieved 2026-10-26
    storage:
      service: Google Cloud Storage
      tier: Standard storage, single region us-central1
      price_per_gib_month: 0.020
      verified: false
      source: Google Cloud Storage pricing page (per GiB-hour rate x 730 h), retrieved 2026-10-26
  azure:
    region: eastus (East US)
    cpu:
      service: Azure Virtual Machines
      machine_type: Standard_D2s_v5
      vcpus: 2
      terms: pay-as-you-go, Linux
      price_per_hour: 0.096
      verified: false
      source: Azurespeed (Azure Retail Prices API) and Holori, retrieved 2026-10-26
    gpu:
      service: Azure Virtual Machines
      machine_type: Standard_NC4as_T4_v3
      accelerator: 1x NVIDIA T4 16 GB
      terms: pay-as-you-go, Linux
      price_per_hour: 0.526
      verified: false
      source: CloudOptimo, retrieved 2026-10-26; the only single-A10 alternative is Standard_NV36ads_A10_v5 at 3.20 (36 vCPU)
    storage:
      service: Azure Blob Storage
      tier: Hot tier, LRS, first 50 TB per month
      price_per_gib_month: 0.0208
      verified: false
      source: Lucidity (Azure Retail Prices API, June 2026), retrieved 2026-10-26; other guides list 0.018
---

# Price Book

**Purpose:** the coefficients that turn recorded usage into Cost per Resolution (CpR), the five-component cost defined in `docs/tracking/metric_contract.md` §3. The YAML block above is the single source: `helios/evaluation/cost.py` reads it and records its SHA-256 with every cost.

**Status:** price-book-v2 (S1.10, 2026-10-26; deviation entries 42 and 43). **Primary provider: AWS**; GCP and Azure are sensitivity profiles. **Frozen at tag `build-freeze`** (S5.3); any change before then is a new deviation entry, none after.
**Owner:** researcher. Entries with `verified: false` are to be checked against the provider's own price list (see *How to verify*); coefficients marked *assumption* are owner decisions to confirm before build-freeze.

---

## Cloud profiles (infrastructure and storage)

Each profile names the exact service, machine type, region and pricing terms, so every number can be looked up and replaced. CPU is priced per vCPU-hour (instance price ÷ vCPUs); GPU per instance-hour of the smallest single-GPU machine that serves an 8B model; storage per GiB-month.

| Provider (region) | Component | Service | Machine type / tier | Terms | Price | Per unit | Verified |
|---|---|---|---|---|---|---|---|
| **AWS** (us-east-1) — primary | CPU | Amazon EC2 | `m5.large` (2 vCPU, 8 GiB) | on-demand, Linux | 0.096 / h | 0.048 per vCPU-hour | ✅ AWS price data, 2026-10-23 |
| | GPU | Amazon EC2 | `g5.xlarge` (1× NVIDIA A10G 24 GB, 4 vCPU) | on-demand, Linux | 1.006 / h | 1.006 per GPU-hour | ✅ AWS price data, 2026-10-23 |
| | Storage | Amazon S3 | S3 Standard, first 50 TB | — | 0.023 / GiB-month | | ❌ third-party |
| **GCP** (us-central1) | CPU | Compute Engine | `n2-standard-2` (2 vCPU, 8 GiB) | on-demand, no CUD/SUD | 0.0971 / h | 0.04855 per vCPU-hour | ❌ trackers disagree (0.0971 vs 0.0777) |
| | GPU | Compute Engine | `g2-standard-4` (1× NVIDIA L4 24 GB, 4 vCPU) | on-demand | 0.7068 / h | | ❌ Google page, region not shown |
| | Storage | Cloud Storage | Standard, single region | — | 0.020 / GiB-month | | ❌ |
| **Azure** (eastus) | CPU | Virtual Machines | `Standard_D2s_v5` (2 vCPU, 8 GiB) | pay-as-you-go, Linux | 0.096 / h | 0.048 per vCPU-hour | ❌ |
| | GPU | Virtual Machines | `Standard_NC4as_T4_v3` (1× NVIDIA T4 16 GB, 4 vCPU) | pay-as-you-go, Linux | 0.526 / h | | ❌ |
| | Storage | Blob Storage | Hot, LRS, first 50 TB | — | 0.0208 / GiB-month | | ❌ guides list 0.018–0.0208 |

**The GPUs differ** (A10G, L4, T4 run an 8B model at different speeds), so per-hour GPU prices are not like-for-like across providers. Pricing per token (GPU price ÷ measured tokens per hour on that GPU) would remove the difference; it needs a throughput benchmark on each reference GPU (open point).

## Shared coefficients (all profiles)

| Component | Coefficient | Value | Source |
|---|---|---|---|
| Token | per million prompt / completion tokens | 0 / 0 | The confirmatory runs use local inference (llama3.1:8b on Ollama, deviation entry 25). The metric contract records local token cost as zero; tokens are still counted (LLM gateway) and their model time is priced as GPU time |
| Storage | retention, months | 1 | *Assumption:* incident telemetry kept for one month |
| Human time | per hour | 63.98 | U.S. BLS, software developers, median annual wage May 2024: 133,080 / 2,080 working hours ([BLS OOH](https://www.bls.gov/ooh/computer-and-information-technology/software-developers.htm)). Wage only, no overhead multiplier |
| Human time | review minutes per human-requesting verdict | 15 | *Assumption:* one engineer review of a PROVISIONAL verdict with a HITL request or a non-converged case; an automatic CONFIRMED verdict carries none |
| Opportunity | per minute of unresolved incident | 5,600 | The per-minute downtime figure the dissertation already uses (Ch2 financial-impact table, citing Chakraborty et al., 2024; commonly attributed to Gartner, 2014). See the caveat below |
| Opportunity | TTCD censoring, seconds | 1,800 | Metric contract §4: an incident with no correct published verdict is censored at Ch3's 30-minute incident window |

## How to verify (official sources)

Replace a value by editing its `price_per_hour` / `price_per_gib_month`, `source` and `verified` in the YAML block, then log a deviation entry.

| Provider | Where to look | Filter |
|---|---|---|
| AWS EC2 | [EC2 On-Demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/), or the public JSON the page loads: `https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/US%20East%20(N.%20Virginia)/Linux/index.json` (gzip) | Region US East (N. Virginia), Linux, instance type `m5.large` / `g5.xlarge` |
| AWS EC2 (CLI) | `aws pricing get-products --region us-east-1 --service-code AmazonEC2 --filters Type=TERM_MATCH,Field=instanceType,Value=m5.large Type=TERM_MATCH,Field=location,Value="US East (N. Virginia)" Type=TERM_MATCH,Field=operatingSystem,Value=Linux Type=TERM_MATCH,Field=tenancy,Value=Shared Type=TERM_MATCH,Field=preInstalledSw,Value=NA Type=TERM_MATCH,Field=capacitystatus,Value=Used` | Needs any AWS login; the price is under `terms.OnDemand` |
| Amazon S3 | [S3 pricing](https://aws.amazon.com/s3/pricing/) → Storage | US East (N. Virginia), S3 Standard, first 50 TB |
| GCP Compute Engine | [VM instance pricing](https://cloud.google.com/compute/vm-instance-pricing) (n2) and [accelerator-optimized pricing](https://cloud.google.com/products/compute/pricing/accelerator-optimized) (g2) | Region us-central1, on-demand |
| Google Cloud Storage | [Cloud Storage pricing](https://cloud.google.com/storage/pricing) | Standard, Iowa (us-central1) |
| Azure VMs | [Linux VM pricing](https://azure.microsoft.com/pricing/details/virtual-machines/linux/), or the public Retail Prices API: `https://prices.azure.com/api/retail/prices?$filter=armRegionName eq 'eastus' and armSkuName eq 'Standard_D2s_v5' and priceType eq 'Consumption'` | Linux rows (no "Windows" in `productName`), `unitOfMeasure` 1 Hour |
| Azure Blob Storage | [Blob pricing](https://azure.microsoft.com/pricing/details/storage/blobs/) | East US, Hot, LRS, first 50 TB |

## Caveats (for the chair call)

- **Opportunity cost dominates.** At 5,600 per minute a single censored incident costs 168,000, against cents of compute; Ch3 §3.8.4 anticipates this and reports components descriptively. The cloud profiles mainly move the compute components, so a compute-only CpR (token + infrastructure + storage) is worth reporting descriptively beside the total.
- **The 5,600 figure is weakly sourced.** It is widely attributed to a 2014 Gartner blog post rather than a study; later surveys give higher values (Ponemon 2016, about 9,000 per minute; EMA, 14,056 per minute, via [BigPanda's EMA eBook](https://start.bigpanda.io/rs/778-UNI-965/images/EMA_Outage_BigPanda_eBook.pdf)). It is kept for consistency with Ch2; a sensitivity analysis at the EMA value is proposed.
- **Local hardware.** Model time measured on the local machine is priced at the reference GPU's hourly rate, which assumes equal speed; the throughput benchmark (open point) checks it.

## What each component measures

See `docs/tracking/metric_contract.md` §3 and `docs/sprints/s1-data-graph/s1_10_price_book_cost.md`.

| Component | Usage recorded | Where it comes from |
|---|---|---|
| Token | prompt and completion tokens of every model call, retries included | LLM gateway (`helios/pipelines/l_pipe/gateway.py`) → `PipelineVerdict.cost` |
| Infrastructure | HELIOS process CPU time per pipeline call; model compute time (server-side prompt evaluation + generation) as GPU time | Orchestrator (`_dispatch`) and LLM gateway |
| Storage | bytes of the incident's telemetry streams | `cost.window_bytes` |
| Human time | whether the published verdict requests a human | MAHC verdict state (S2) |
| Opportunity | time to correct diagnosis, censored at 1,800 s | TTCD (S2 / evidence runs) |
