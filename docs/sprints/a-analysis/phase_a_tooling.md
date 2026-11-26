# Phase A tooling and rehearsal on build data

**Date:** 2026-11-26 · **Data:** build data only (`data/campaigns/s5_cr`); the pool stays locked · **Code:** `scripts/phase_a_tables.py`, `scripts/phase_a_evidence.py`, `scripts/phase_a_bundle.py`, with tests in `tests/test_phase_a_*.py`

## 1. Why

A rehearsal of phase A on build data checks, before E1, that every A1–A6 output can be produced from what phase E will store. The span-status defect (entry 104) showed that build data hides problems.

## 2. What the frozen analysis already covers (A1–A3)

`bin/analyse.py` runs in 2–4 seconds per store. It produces:
- Family A and Family B, with binding Holm, the other Holm reading and Benjamini–Hochberg;
- group-level Wilcoxon;
- the rank mixed model with ICC;
- MCAR / IPW;
- trigger-time baselines (B-b) and CpR without human time;
- rerun determinism, the sanity floors and the timing-noise statement (entries 94–96).

## 3. Defect found and fixed: the confirmatory guard

The guard accepted only the 8 confirmatory variant hashes, so the pool store (E1, E2 and E3 in one file) could never be labelled confirmatory. It is fixed under entry 108 and frozen as `build-freeze-4` (entry 109).

Rehearsal result: every p-value and all 48 decision rows per store are identical; only the label changes. Design note: `docs/sprints/e-evidence/guard_fix_design.md`.

## 4. New scripts (outside the frozen paths)

All three live in `scripts/`, which is not a frozen path, so phase A can refine them without a new freeze. None of them computes a test statistic, reads ground truth or prints a case ID. `bin/build_freeze.py --check` still reports the frozen build with them present.

| Script | Task | Reads | Writes |
|---|---|---|---|
| `phase_a_tables.py` | A6, T-j's Markdown tables | the analysis JSON only | One Markdown file: systems, trace coverage, Family A and B (test, n, p, Holm threshold and decision, mean difference with BCa, Hodges–Lehmann, Cliff's δ, Cohen's h), robustness, HR@1 and MRR beside HR@3, Family B sensitivity, Family E, floors, determinism |
| `phase_a_evidence.py` | A5, C1 and innovation evidence | scored stores and campaign logs | JSON and Markdown, sections below |
| `phase_a_bundle.py` | A6, replication bundle | freeze record, deviation anchor, `research/osf/`, campaign inputs, output artefacts | Manifest JSON and README with SHA-256 digests and reproduction steps; it warns if a campaign was planned under another build |

**The label rule.** The tables say "rejected" only for a confirmatory run. Any other run reads "below threshold (descriptive)", and a test checks that the word "rejected" never appears there.

**The evidence sections:**
- **Narratives:** written by the model or filled by the template; claims drafted and rejected by the verifier; model attempts; H_struct.
- **Calibration:** Brier, ECE, AUROC and reliability bins, plus reliability per published state with the CR-03 reason.
- **Routing:** HELIOS-Full against HELIOS-noRouter on paired cases.
- **Integrity:** exclusions by gate check.

**What the bundle records:** the build commit and tag, the record digest and the frozen-paths digest read by name, the deviation-log head, the deposit digests, the store digests and the BCa seeds. S4.11 T-j asked the analysis JSON to carry the input digests, the plan hash and the seeds; the frozen `bin/analyse.py` does not, so the bundle records them beside it.

## 5. Rehearsal readings (build data, exploratory, descriptive)

**RCAEval build (495 cases in three parts):**
- **Routing:** HELIOS-Full consults the L-pipe in 46.5% of cases, against every case for noRouter. It saves 47.7% of pipeline tokens. Median TTT is 228 ms against 9,272 ms, and median log-CpR 3.67 against 6.79. HR@1 changes by −0.008 and HR@3 by −0.006.
- **Calibration (Full):** mean confidence 0.964 against an observed HR@3 of 0.968; Brier 0.032, ECE 0.011, AUROC 0.718. For noRouter the AUROC is 0.815.
- **State reliability (Full, HR@3):**
  - "confirmed: two or more pipelines, confidence above floor": 0.956 (n 180);
  - "provisional: one pipeline ran": 0.981 (n 266);
  - "provisional: confidence below floor": 0.939 (n 49).
  These match the CR-03 note.
- **Narratives:** the verifier rejected none of the claims drafted for any narrating variant. The Full narrator needs 2.2 model attempts per narrative.
- **Integrity:** 1,229 of 12,075 run keys excluded: 990 for an absent modality, 239 for baseline errors.

**OTel build v3 (63 cases):** the tables reproduce the analysis. A-H5 is the only Family A hypothesis below its Holm threshold, and all Family B hypotheses are below theirs.

## 6. Open items

| Item | Why open | Owner decision needed |
|---|---|---|
| **E-H5 on the pool** | Entries 75 and 92 make E-H5 a reward replay over a seeded 25% of each pool corpus after scoring. `bin/reward_replay.py --corpus pool` refuses the pool unconditionally, and the campaign's "E-H5 subset" (60 cases) is listed but runs nothing. A tool that reads pool ground truth from outside the frozen build touches D11. | Yes: build the pool replay as a frozen-build change (entry, new freeze) before E1, or report E-H5 on build data only |
| **Figures** | No plotting library is installed. Adding one changes `pyproject.toml` and `poetry.lock`, which are frozen files. Options: plain SVG written by a script, or figures made outside the Poetry environment from the JSON outputs. | Choice of route, no entry either way |
| **E-H4 and E-H6 on the pool** | Each needs its own campaign (`--fgsv-perturb`, `--iol-inject`). Phase E does not schedule either; Stage B (B5) covers their full forms. | Whether to run reduced forms in phase E |
