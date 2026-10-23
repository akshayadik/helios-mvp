# S0.1 — Dataset check (RCAEval, AIOpsLab)

**Date:** 2026-10-23 · **Tracking:** S2-M5-RES01 · **Plan:** `helios_e2e_product_plan_2026-10.md` §5 S0.1 · **Feeds:** D11 (corpus and run design)

**Verdict:** **RCAEval — GO** as the primary recorded corpus, with four design requirements (§4). **AIOpsLab — feasible on this machine; run a two-day recording spike in S1** before deciding whether it joins Stage A or Stage B.

Everything below was checked against primary sources (the repositories, the dataset index and one downloaded case), not taken from the README alone. Nothing was changed in the repository; downloaded data stayed in a scratch folder.

---

## 1. Licences

| Source | Licence | Use for HELIOS |
|---|---|---|
| RCAEval code (`github.com/phamquiluan/RCAEval`) | MIT; bundled baseline methods carry their own licences in `LICENSES/` | Baselines run in a separate environment; check each chosen baseline's licence in D5 |
| RCAEval data, Hugging Face copy (`huggingface.co/datasets/phamquiluan/RCAEval`, Parquet, 3.4 GB) | MIT | Recommended copy: downloadable per case |
| RCAEval data, Zenodo archive (record 14590730, DOI 10.5281/zenodo.14590730, 5.2 GB zip) | CC BY 4.0 | Citation required |
| AIOpsLab (`github.com/microsoft/AIOpsLab`) | MIT | Framework only; we record our own telemetry |

Cite: Pham et al., "RCAEval: A Benchmark for Root Cause Analysis of Microservice Systems with Telemetry Data" (arXiv 2412.17015).

---

## 2. What RCAEval actually contains (counted from `cases.parquet`)

735 labelled cases. Each case has its root-cause service, fault type, repetition number, injection time, and per-modality presence flags.

| Dataset | System | Cases | Logs | Traces | All three modalities |
|---|---|---|---|---|---|
| RE2-OB | Online Boutique | 90 | 90 | 90 | **90** |
| RE2-TT | Train-Ticket | 90 | **89** | 90 | **89** |
| RE2-SS | Sock Shop | 90 | 90 | **0** | 0 |
| RE3-OB | Online Boutique | 30 | 30 | 30 | **30** |
| RE3-TT | Train-Ticket | 30 | 30 | 30 | **30** |
| RE3-SS | Sock Shop | 30 | 30 | 0 | 0 |
| RE1 (OB, SS, TT) | all three | 375 | 0 | 0 | 0 |

- **239 cases have metrics, logs and traces** (RE2-OB 90, RE2-TT 89, RE3-OB 30, RE3-TT 30). This is the pool that exercises every HELIOS pipeline.
- **The README is slightly wrong:** it says RE2-TT has logs, but `re2tt_ts-auth-service_cpu_1` has none. The integrity gate must exclude it with a ledger entry or include it with a missing-logs covariate — never impute.
- RE2 fault types: cpu, mem, disk, delay, loss, socket; each of 5 services × 6 faults × 3 repetitions. RE3 holds code-level faults (f1–f5), a different fault family.
- Windows: about 24 minutes per case (half before injection, half after); RE2-OB traces median about 400k spans, RE2-TT about 780k.

### One case inspected (`re2ob_checkoutservice_cpu_1`, 10.6 MB)

| File | Shape | Contents |
|---|---|---|
| `traces.parquet` | 392k spans × 11 | `traceID, spanID, parentSpanID, serviceName, methodName, operationName, startTime, duration, statusCode` — enough to build the call graph |
| `logs.parquet` | 171k × 3 | `timestamp, container_name, message` — no level field; template extraction applies |
| `metrics.parquet` | 1,441 steps × 73 | `<service>_<metric>` columns (cpu, mem, diskio, latency, …) |
| `inject_time.txt` | — | Unix timestamp of injection |

---

## 3. Findings that change the design

| # | Finding | Consequence |
|---|---|---|
| F1 | **The case ID contains the answer** (`re2ob_checkoutservice_cpu_1` names the root-cause service and the fault) | The adapter assigns **opaque incident IDs**; the real case name lives only in the ground-truth file. A test proves no case name, service-label or fault string reaches any pipeline input or LLM prompt |
| F2 | **Root causes are concentrated:** each system injects faults into only 5 services. Guessing at random among those 5 gives **HR@3 = 3/5 = 0.60** — the same value as the CHASE-adjusted baseline | HELIOS never receives the candidate set: it ranks over **all** services of the system (11 in Online Boutique, dozens in Train-Ticket). The analysis reports a **prior-only sanity floor** and a leave-one-service-out check |
| F3 | **RE1 and RE2 share their root-cause services** (identical in Sock Shop and Train-Ticket; 3 of 5 in Online Boutique) | RE1 is not "unseen" calibration data. Trained components (the G-pipe ranker, router initialisation, MAHC calibration) use **service-agnostic features only** (anomaly scores, graph position, error rates, latency shifts), never service names |
| F4 | **Service names differ by modality** (`frontendservice` in traces, `frontend` in metrics) | A per-system name-normalisation table in the adapter, tested |
| F5 | **Trace coverage is partial** (the inspected case: 7 services in traces, 11 in metrics) | The incident graph must add services seen only in metrics or logs, with their missing edge kinds recorded |
| F6 | One RE2-TT case lacks logs | Handled by the integrity gate (see §2) |

---

## 4. Requirements for D11 (corpus and run design)

1. **Confirmatory pool:** the 239 full-modality cases, partitioned before any confirmatory run. RE2-SS (no traces) and RE1 (metrics only) are candidates for calibration and for modality-ablation context, labelled as such.
2. **Calibration partition** chosen with a registered seed, stratified by system and fault; because of F3, its purpose is tuning service-agnostic parameters, not learning which services fail.
3. **Leakage tests** in the adapter (F1) and a **feature audit** of every trained component (F3), both before the freeze.
4. **Sanity floors in the analysis:** prior-only HR@3 (F2), random over all services, and leave-one-service-out.
5. **Power:** 239 paired cases exceed the n = 174 used in Ch3's power analysis, but cases are clustered (5 services × 6 faults × 3 repetitions per system); D11 must account for that clustering (e.g. the rank-based mixed model Ch3 already lists as sensitivity).

---

## 5. AIOpsLab feasibility

| Item | Finding |
|---|---|
| What it is | An interactive framework: deploys microservice apps, injects faults, generates load, exports telemetry; about 86 problem definitions |
| Runs on | Local `kind` cluster (ARM config available) or cloud VMs (Terraform + Ansible) |
| This machine | Apple M5 Pro, 18 cores, 64 GB memory, 615 GB free disk, Docker 29.5 running, `kubectl` present; `kind` and `helm` not installed (one-line installs) |
| Effort | Recording a corpus means deploying each app, injecting each fault and exporting telemetry ourselves |

**Recommendation:** a **two-day spike in S1** — install `kind` and `helm`, record one problem end to end into the HELIOS sealed format. If one problem records cleanly within a day, AIOpsLab joins Stage A as a second confirmatory system (stronger external validity); otherwise it moves to Stage B. Either way RCAEval carries Stage A.

---

## 6. Status

- RCAEval: **GO**.
- AIOpsLab: **spike in S1**.
- Feeds D11 (S0.3), which is prepared for the owner's review before OSF deposit 1.
