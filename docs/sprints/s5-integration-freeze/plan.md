# Sprint S5 — Integration and freeze · plan

**Window:** 1–12 Feb 2027 (10 working days). Can start early once the owner confirms, as S1–S4 did; S4 closed on 2026-11-14, about eleven weeks before this window. · **Milestone:** S2-M10 · **Exit tag:** `build-freeze` · **Status:** planned. Refreshed 2026-11-14 with the S4 carry-overs, capacity and owner items.

Task details: `docs/tracking/helios_task_breakdown.md` § Sprint S5 (authoritative).

## Goal

Prove every variant runs end to end, certify the flags, pilot the whole pipeline on build data, then freeze the evidence build and deposit the freeze addendum on OSF. **Stage A build complete.**

## Entry conditions

| Condition | State (2026-11-14) |
|---|---|
| `rb-s4-exit` | **Met**: annotated tag on `5cd8b37`, pushed. PR #99 (exit report and documentation sync) merged as `6a034ce` |
| Rating rubric trialled and ready to freeze (S2.9, row S2-M7-RES01) | **Not met**: the design is approved (R-a to R-o) and the instrument is built, but rater training needs rater 2 (due 30 Nov). This blocks only S5.7 (deposit 2 carries the frozen rubric), not S5.1–S5.5 |
| Working tree clean of unregistered data | **Met**: only edit-audit lines in `experiments/experiment_log.csv` and the two kept local edits in the demo submodule |
| S2-M10 tracking rows added | **Done with this refresh**: RES01, EVAL01–EVAL05, GATE01–GATE03, all PLANNED |

## Proposed split: verify now, freeze when its inputs are ready

S5 has two parts with different gating:

- **Verification (S5.1–S5.5 and RES01).** This part needs only build data and the S4 code. It changes no frozen parameter, and the pool stays locked. Nothing stops it from starting now.
- **Freeze and deposit (S5.6, S5.7).** These are one-way: after `build-freeze`, any change is a deviation with rerun or exclusion. They need inputs that do not exist yet:
  - the frozen rubric (rater 2 and training);
  - the E-H5 addendum decision;
  - the GCP and Azure price-book profiles;
  - the chair call at the end of November, whose feedback is cheaper to absorb before the freeze than after it.

**Recommendation:** start the verification part now. Run S5.6 and S5.7 as soon as their inputs are in. Then confirm whether phase E starts early too, which needs the phase E entry conditions: raters trained, compute decided and, for E4 only, IRB.

A freeze in December would leave about two months of slack before the 2027-03-31 results deadline. A freeze held until 12 February leaves none.

## Carried in from S4 (exit 2026-11-14)

From the [S4 exit report](../s4-product-eval-tooling/exit_report.md) §6.

| Item | Where it goes |
|---|---|
| `ablation_architecture.md` stale for S4: CoE steps A (FGSV) and S (self-telemetry), the API, the console and the compose shell (register row 1) | RES01 |
| `r1_traceability_matrix.md` §2 note: FGSV and IOL are now built as lite versions (entry 89) (register row 21) | RES01 |
| OSF addendum draft (S3 plan § OSF addendum) has no S4 items yet. Add the bullets for entries 84–89 and the S4 frozen files (`fgsv_params.json`, `iol_injection.json`, `narrative_tau.json`) | RES01 drafts it; the owner deposits it before `build-freeze` |
| S5.1 system test includes noFGSV and noIOL; noCogni and HIS3 stay refused | S5.1 |
| S5.3 pilot joins `determinism.json` into `eval_run` (left to the pilot by S4.10) | S5.3 |
| Pool-only checks after `build-freeze` (span status-code format, rebuilt series; S4.8 open item) | Phase E first day, after S5.6 |

## Found during this refresh

**S5.2 disjointness: the audit sees only decorators.** `python -m helios.vcl.disjointness` passes today but lists 11 of the 16 boolean flags as UNCOVERED, because it counts only `@gated_by(VCLFlag.X)` entry points. Eight of the 11 have a consumer that reads the manifest instead of a decorator:

- `ueg_structural`: graph builder, pruners, D- and G-pipe;
- `fgsv_ks_gate`, `iol_self_telemetry`, `coe_narrative` and `cbr_routing`: runner;
- `acp_stateful`: ACP predictor and runner;
- `reconcile_terminal`: reward ledger and replay;
- `dpipe_propagation`: D-pipe.

The other three have no consumer: `p4_cognitive`, `his_tier` and `sampling_regime_tag`. noCogni and HIS3 are already refused by the schedule. `sampling_regime_tag` belongs to no variant.

"Zero uncovered" therefore needs two things:

1. **Coverage of the eight manifest readers.** Either the audit learns to recognise manifest reads, or each reader gets a decorated entry point. The audit change is preferred: it leaves the gated code untouched.
2. **A declared, tested no-consumer list** for the other three. The certificate states that these flags gate nothing in Stage A, and the schedule refuses any variant that differs from Full only in them.

The CI job's dynamic step also names a context `HELIOS-noGraph` that is no longer a variant, so it must be updated to real variant names.

Neither fix touches `variants.py` or any variant hash.

## Capacity

The breakdown's tasks come to 8 days. The carried-in work adds about 2 days: RES01 documentation and the addendum draft (1), and the S5.2 audit extension (1). That is 10 days of work against 10 working days, so the February window alone has **no slack**. Starting the verification part now gives about eleven weeks in hand.

Order of work:

| Step | Work | Why this order |
|---|---|---|
| 1 | S5.2 disjointness certification, with the audit extension | Cheapest check, and it can change code; it must come before the system test that certifies the variants |
| 2 | S5.1 system test of all 15 variants (13 run, 2 refused with reasons) | Proves that S5.3 has something to pilot |
| 3 | S5.5 LLM determinism probe | Short. Its token-equality rate feeds the pilot report |
| 4 | S5.3 exploratory pilot on build data (with the `determinism.json` join) | Gives the numbers for owner decisions L5–L7 |
| 5 | S5.4 clean-environment replication | Run last, on a fresh checkout of the commit to be frozen |
| 6 | RES01 documentation carry-ins and the addendum draft | Alongside steps 1–5; the draft must be ready before S5.6 |
| 7 | S5.6 build freeze → S5.7 OSF deposit 2 | When the freeze inputs are in (see the proposed split) |
| 8 | GATE03 S5 exit | Exit report and documentation sync |

## Tasks

| Task | Tier | Tracking | Effort | Done when |
|---|---|---|---|---|
| S4 documentation carry-ins and OSF addendum draft | — | S2-M10-RES01 | 1 | `ablation_architecture.md` and the R1 §2 note updated (register rows 1 and 21 current); addendum draft covers entries 46–89 and the S4 frozen files |
| S5.1 System test of every variant | T1 | S2-M10-EVAL01 | 2 | 15 variants run end to end on build data (noCogni and HIS3 refused with the recorded reason) |
| S5.2 Disjointness certification | T1 | S2-M10-EVAL02 | 1 + 1 | Every boolean flag gates exactly one code path; zero uncovered, with the three no-consumer flags declared and tested |
| S5.3 Exploratory pilot on build data | T1 | S2-M10-EVAL03 | 2 | Pilot report labelled exploratory; metrics, cost and timing populated |
| S5.4 Clean-environment replication | T1 | S2-M10-EVAL04 | 1 | Snapshot hashes and fused rankings reproduce on a fresh checkout |
| S5.5 LLM determinism probe | T1 | S2-M10-EVAL05 | ½ | Token-equality rate measured |
| S5.6 Build freeze | T1 | S2-M10-GATE01 | 1 | Tag `build-freeze`; VCL blocks any divergence |
| S5.7 OSF deposit 2 (freeze record + rating rubric) | T1 | S2-M10-GATE02 | ½ + upload | DOI in the deviation log |
| S5 exit gate | — | S2-M10-GATE03 | — | Exit criteria below |

### Existing code each task starts from

| Task | Starts from |
|---|---|
| S5.1 | `bin/helios_campaign.py` and `helios/orchestrator/{schedule,campaign,runner}.py`: the schedule's refused set (HIS3, noCogni) |
| S5.2 | `helios/vcl/disjointness.py` (static audit), `.github/workflows/disjointness_audit.yml` (dynamic step) |
| S5.3 | `bin/score_runs.py`, `bin/analyse.py`, the S4.9 metrics suite, the S4.10 determinism compare |
| S5.4 | The pre-push gate and `bin/verify_captures.py`, on a clone outside the working tree |
| S5.5 | The L-pipe gateway and response cache (bypassed for the probe, as the S4.10 determinism rerun does) |
| S5.6 | `bin/verify_osf_freeze.py`, `data/frozen/`, `helios/vcl/snapshot_registry.py` |

## Owner items

| Item | Source | Needed by |
|---|---|---|
| Confirm starting S5.1–S5.5 and RES01 now; S5.6 and S5.7 when their inputs are in (proposed split above) | This refresh | Before S5 work starts |
| Rater 2 and adjudicator (L2, L3; row S2-M5-RES05) | Carried since S0 | 30 Nov 2026 |
| S2.9 rater training to κ ≥ 0.7 and rubric freeze (row S2-M7-RES01) | S2 exit | Before S5.7 |
| E-H5 addendum decision (RRE selection between Full and noReconcile; S4.11 builds both forms) | S3 exit §6 | Before S5.6 |
| GCP and Azure price-book profiles checked | S1 carry-over | Before S5.6 |
| OSF addendum deposit (draft from RES01) | S2-BL-05 | Before S5.6 |
| Compute (L5), 70B subset (L6), judge models (L7), decided from the S5.3 pilot numbers | S0.11 | When the pilot report is ready, no later than 5 Feb 2027 |
| OSF upload for deposit 2 (same account as deposit 1) | S5.7 | After S5.6 |
| IRB approval for RQ4 (E4 in phase E only) | S0.11 L1 | 2027-02-05 |
| Back up `.env`, `.env.labelling`, `data/cache/lpipe_cache.sqlite`, `data/labelling/build`; confirm the key backups (L10) | S2-BL-17, -19 | Now |
| Hook commands use `$CLAUDE_PROJECT_DIR` (approve the `.claude/settings.json` change) | Open since S0 | Any time |
| Chair call (end of November): call-reference doc with an outcomes table; agenda in the S4 exit report | S3 and S4 exits | Prepared from about 2026-11-20 |

## Expected deviation entries

- S5.2 audit change and the no-consumer declaration, if the certificate changes what entry 31 says about the flag set (no variant hash changes either way).
- Freeze record: commit SHA, image and model digests, parameter hashes, price book, pool manifest.
- Rubric hash (entry 38 follow-up).
- The deposit-2 DOI.
- Tier-2 items moved to Stage B: expected none, since all four were built in S4.

## Exit criteria

S5.1–S5.7 and RES01 DONE; tag `build-freeze`; deposit-2 DOI in the deviation log; full gate green on main; exit report written, with the status of every carried-in item above.

## Risks

| Risk | Mitigation |
|---|---|
| A defect found after the freeze | Phase E rule: deviation entry; rerun or exclude with ledger entries, never edit |
| Chair-call feedback asks for a change to the evidence build | Freeze after the call (proposed split); a change after the freeze goes through a deviation entry |
| Rater 2 is late, so the rubric cannot freeze | S5.1–S5.6 do not depend on it; S5.7 and E5 wait; the freeze record is still written |
| The audit extension misses a manifest read and certifies an uncovered flag | The dynamic step (coverage contexts per variant) cross-checks the static audit; a test plants an unread flag and expects UNCOVERED |
| The pilot shows the campaign does not fit phase E on local hardware | D11 recheck gives about 5–6 h central for E1 + E3; decide on rented compute (L5) from the pilot |
| The clean checkout differs from the working tree (untracked data, local submodule edits) | S5.4 runs on a fresh clone of the tagged candidate commit; any difference is fixed before the freeze |
