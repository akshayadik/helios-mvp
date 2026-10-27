# S0.11 — Lead-time register

**Opened:** 2026-10-24 · **Owner:** AA · **Tracking:** S2-M5-RES05 · **Companion to:** `helios_task_breakdown.md` (S0.11), `helios_e2e_product_plan_2026-10.md` (§ Resources, § Risks)

Items with a long lead time that only the owner can start, each with the date it is needed by and the task it blocks. The row stays IN_PROGRESS while items are open; it closes when every item is either done or has a dated decision. Update the **Status** column in place; a change of plan that alters what a pre-registered test measures still needs a deviation entry.

"Needed by" is the latest date that keeps the plan on schedule. Dates marked *(assumed)* rest on a turnaround nobody has confirmed yet; replace them when it is known.

---

## 1. Register

| # | Item | Owner | Needed by | Blocks | Status |
|---|---|---|---|---|---|
| L1 | IRB application for the RQ4 user study (D12) | AA | Submit by 2026-12-04 *(assumed: about eight weeks' turnaround over the holidays)*; approval by 2027-02-05 | E4 (runs 15 Feb – 12 Mar only if approved by early February) | Submission date not yet set (2026-10-24) |
| L2 | Second rater for H_fact (two raters, blind to variant, κ ≥ 0.7) | AA | Confirmed by 2026-11-30 | S2.9 training (January), E5 | Not started |
| L3 | Standby adjudicator (re-labels when κ < 0.7) | AA | Confirmed by 2026-11-30 | E5 | Not started |
| L4 | Rating rubric, blind labelling tool, rubric in OSF deposit 2 | Claude (S2.9) | Rubric drafted by 2026-12-23; frozen after training; deposited at S5.7 | Rater training, E5 | Added as task S2.9 |
| L5 | Compute for the 8B confirmatory runs | AA (decision) | 2027-02-05 (S5.3 pilot measures time per incident) | E1, E3 | Local first: llama3.1:8b already on this machine |
| L6 | Budget decision: 70B sensitivity subset (RB2, E6) | AA | 2027-02-05 | E6 | Open; options in §3 |
| L7 | Budget decision: judge models for FAE (optional, E5) | AA | 2027-02-05 | E5 (optional part only) | Open |
| L8 | Baseline environments for B1–B5 and the alternates | Claude | Before S4.8 (2027-01-18) | S4.8, E2 | Spike done 2026-10-24: both environments build and every agreed method imports; B4 needs an adapter (§4) |
| L9 | Docker Desktop memory raised to at least 16 GB | AA | Before S4.8 (2027-01-18) | S4.8, E2 | **Done** (owner, during S1): raised to 16 GB; the S1.2 campaign ran on it |
| L10 | Backups: `DEVIATION_ED25519_PRIVATE_KEY` and `DEVIATION_HMAC_SECRET` in the password manager; `osf_deposit_1.zip` moved out of the repo and kept | AA | Now | Every future deviation entry; deposit-1 audit trail | Open |

---

## 2. Second rater and adjudicator (L2, L3)

**What the protocol requires** (metric contract, deposited at OSF deposit 1; Ch3 §3.8): two independent raters, blind to variant, label **every** published narrative of HELIOS-Full and HELIOS-noLLM — 480 narratives each (240 cases × 2 variants). Cohen's κ ≥ 0.7; below that, a third adjudicator re-labels. Raters first calibrate on 50 instances from build data.

**Who qualifies.** Incident-response or SRE experience with microservices: able to judge whether a statement about a service, metric, log or trace is supported by the evidence shown. Not involved in building HELIOS; not an RQ4 participant.

**What to agree with them in writing** (an email is enough):
- Time: about 30–40 hours *(estimate: 530 items at about four minutes each, plus training; check it in training)*.
- Schedule: training in January (S2.9), confirmatory labelling during phase E (15 Feb – 12 Mar) as narratives become available.
- Confidentiality of the system and the cases; a short conflict-of-interest declaration.
- Payment or acknowledgement.

**IRB.** A rater labels system output and is research personnel rather than a research subject; name both raters as personnel in the RQ4 application (L1) and let the IRB confirm that no separate review is needed.

---

## 3. Compute and budget (L5–L7)

- **8B runs (L5).** Confirmatory runs use llama3.1:8b (RB2), already pulled on this machine (Apple M5 Pro, 64 GB). The S5.3 pilot measures wall-clock time per incident; multiplied by the run schedule (1,920 variant runs plus exploratory variants) it gives the campaign time. Only if that does not fit phase E is a rented GPU needed.
- **70B sensitivity (L6).** Two options: (a) local, a 4-bit 70B model needs roughly 40–45 GB and fits in 64 GB of unified memory, but generates slowly — the pilot measures how slowly; (b) rented GPU for the subset only. Decide after the pilot; the subset size sets the cost.
- **Judge models (L7).** Optional (E5 "judges if budget"); the pilot's token counts per narrative, priced from the price book (S1, `docs/tracking/price_book.md`), give the cost. The rater labels remain the A-H7 measure either way.

---

## 4. Baseline environments (L8) — spike, 2026-10-24

RCAEval (MIT; bundled methods carry their own licences in `LICENSES/`) pinned at commit `2fca61b9730a69c21ef72411844735634dbb010f` (2026-10-20). Two isolated images, base images pinned by digest: `baselines/rcaeval/Dockerfile.default` (Python 3.12) and `baselines/rcaeval/Dockerfile.rcd` (Python 3.8). Neither shares an environment with HELIOS.

| Baseline | RCAEval function | Environment | Finding |
|---|---|---|---|
| B1 multi-source BARO | `mmbaro` | default (3.12) | Imports. Needs multi-source input (metrics, logs, traces): first run in S4.8 |
| B2 TraceRCA | `tracerca` | default (3.12) | Imports. Needs traces: first run in S4.8 |
| B3 BARO (metrics only) | `baro` | default (3.12) | Imports and runs on the sample (under a second) |
| B4 PDiagnose | none — `RCAEval/e2e/pdiagnose.py` is a script | default (3.12) | **Needs an adapter.** The file is a 128-line `main()` hard-wired to one Online Boutique case path; it prints its ranking and is not registered in `RCAEval.e2e` or `main.py`. S4.8 writes a faithful adapter to the common interface (same scoring: ALPHA = 5, 3σ rules on metrics and spans, error/fail log counts) and records every departure from the script |
| B5 multi-source RCD | `mmrcd` | rcd (3.8) | Imports (with `rcd`, which runs on the sample in about 4 s). Needs multi-source input: first run in S4.8 |
| Alternate: CIRCA (metrics) | `circa` | default (3.12) | Imports and runs on the sample (about 1 s) |
| Alternate: CausalRCA | `causalrca` | default (3.12) | Imports and runs, but slowly: 5–7 minutes per case on 8 GB of Docker memory (about a day for 240 cases). Output changes with the seed, so registered seeds matter here |

**Data used.** Only RCAEval's sample file (`simple_data.csv` from the BARO release, metrics only), which is not in the confirmatory pool. Every RCAEval case that carries traces is in the sealed pool (RE2-OB/TT, RE3-OB/TT), so the trace-based baselines (B2, B4) and the multi-source ones (B1, B5) get their first full run on build data in S4.8, on OTel Demo captures converted to RCAEval's format. No baseline is run on pool data before the build freeze.

**Images built 2026-10-24 (arm64):** `helios-baselines-default:2fca61b` (`sha256:bd05e0dcf6d6`, 176 packages pinned in `baselines/rcaeval/constraints-default.txt` because RCAEval's `requirements.txt` uses open ranges; a rebuild reproduced the same set) and `helios-baselines-rcd:2fca61b` (`sha256:54c3079b5b48`, from RCAEval's own lock file). On arm64 the RCD image needed one fix: `scikit-network 0.31.0` has no prebuilt Python 3.8 ARM package and its build script imports numpy, so numpy 1.23.5 (the lock-file version) and Cython 0.29.37 are installed first. Spike runs used no network inside the containers and are not evidence.

**For S4.8.** Raise Docker memory (L9; RCAEval asks for 16 GB and 8 cores). RCAEval's own instructions target Ubuntu 20.04/22.04; the images here use Debian bookworm on arm64, which the spike checks.
