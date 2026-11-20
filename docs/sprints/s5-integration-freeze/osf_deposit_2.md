# OSF deposit 2 · build freeze and frozen rating rubric

**What:** the note and file list for `osf_deposit_2.zip`, the third OSF registration of HELIOS. Deposit 1 is KMR3D (DOI 10.17605/OSF.IO/KMR3D, entry 37) and addendum 1 is VG5TE (DOI 10.17605/OSF.IO/VG5TE, entry fec687b3c173). · **Task:** S5.7, row S2-M10-GATE02. · **Built by:** `git archive` of one commit of this repository, listed paths only, as the earlier deposits were. The commit, the zip's SHA-256 and the DOI are recorded in the deviation entry that records the deposit, and the commit is tagged `osf-deposit-2`.

## 1. What this deposit fixes

Both items are fixed before any confirmatory data is read: the confirmatory pool (RCAEval, 240 cases) was locked until the build was frozen, and no confirmatory narrative existed when the rubric was frozen.

| Item | Value | Entry |
|---|---|---|
| Frozen build | annotated tag `build-freeze` on commit `c4037c0` (2026-11-20) | 101 |
| Build-freeze record | `data/frozen/build_freeze.json`, SHA-256 `c1877063f4a9a1728ee2d10a1e749fe24b31452a99ef5e1e26d1eb062ca72161` | 101 |
| Frozen paths | 245 files under `helios/`, `bin/`, `data/frozen/`, `research/osf/`, `deploy/`, `baselines/`, plus `pyproject.toml`, `poetry.lock`, the price book and the pool manifest; digest `8078c267c95f13faae339448e9c34be7672c203d933a901404b3724e4628d585` | 101 |
| H_fact rating rubric | `docs/research/h_fact_rubric.md`, SHA-256 `f705edb815767f00f5ca84c04359a9edf0d7cd5782d3292d12f657d7a13b01ef` | 102 |

The record also lists, each computed and none typed: the ten frozen parameter files, price book v3, the model (llama3.1:8b, digest from entry 58) with its sampling values and worker prompt hashes, every container image pinned by digest, the 15 variant hashes, the scoring and metrics versions, the deposited analysis plan's SHA-256 and the pool manifest (no label file is read).

## 2. What the freeze means for the confirmatory runs

- **Only the frozen build reads the pool.** The pool unlocks only on a checkout where tag `build-freeze` exists, the record matches the record at the tag, and every frozen file matches the record, with none added, missing or untracked (`helios/vcl/freeze.py`, called by every pool gate through `helios/telemetry/pool_lock.py`). Phase E runs from a checkout of the tag. Development after the freeze (Stage B) continues on `main` and is locked out of the pool.
- **Pool campaigns name their build.** Each confirmatory campaign records the frozen-paths digest when it is planned and refuses to run on another build.
- **Later changes.** Any change to a frozen path after the tag needs a deviation entry with a rerun or an exclusion (D11).
- **Moved to Stage B, before the freeze:** the P4 cognitive layer, HIS tiers and the sampling regime tag (entry 90); E-H8 (entries 82, 83); FGSV full twin, IOL sensitivity beyond the shared detector and NER redaction, whose lite versions are frozen (entry 89).

## 3. The rubric and the labelling of A-H7 (entry 102)

- **Frozen before rater training.** The rubric is frozen now, before rater training, so that it is fixed before the confirmatory results are seen. The design (`docs/sprints/s2-reasoning/s2_9_rubric_design.md`) had planned to freeze it after training.
- **Raters.** Two external raters and one adjudicator with systems experience (R-a, R-l), recruited in December 2026.
- **Training.** Rater training happens on build data only, with the frozen rubric, and must reach κ ≥ 0.7.
- **Rubric changes.** If training shows the rubric must change, the change and its new hash get a deviation entry before confirmatory labelling starts. No change is allowed after that.
- **What is labelled.** Every displayed claim of the 480 HELIOS-Full and HELIOS-noLLM pool narratives, labelled blind (R-b to R-d), with planted checks (R-f).
- **Disagreements and low agreement.** Disagreements go to the adjudicator. If κ is below 0.7, the adjudicator relabels every real claim (R-m, as in deposit 1).
- **A-H7 is tested whatever the other confirmatory results are.** If labelling is not complete by 31 March 2027, A-H7 is reported as incomplete, never dropped.

## 4. Files in the zip

| Path | What |
|---|---|
| `docs/sprints/s5-integration-freeze/osf_deposit_2.md` | This note |
| `docs/research/h_fact_rubric.md` | The frozen H_fact rubric (§3) |
| `docs/sprints/s2-reasoning/s2_9_rubric_design.md` | Rubric and blind labelling design (R-a to R-o) |
| `helios/labelling/sets.py` | Rubric hash and the labelling shuffle seed derived from it (R-o) |
| `data/frozen/build_freeze.json` | The build-freeze record (§1) |
| `docs/sprints/s5-integration-freeze/s5_6_build_freeze_design.md` | Build freeze design (F-a to F-e) |
| `bin/build_freeze.py` | Writes and verifies the record |
| `helios/vcl/freeze.py` | The divergence check |
| `helios/telemetry/pool_lock.py` | The pool lock that asks it |
| `deviation_log.jsonl` | Deviation log, entries one to 102 (HMAC chain; Ed25519 signatures from entry 35) |
| `deviation_log.anchor.json` | Signed head anchor: entry count, head signature, SHA-256 of the whole log |
| `docs/tracking/deviation_log.md` | Readable mirror of the log |
| `keys/deviation_log_ed25519.pub.pem` | Public key that verifies every entry and the anchor |

**Not included, and why:**
- **Files already deposited:** deposit 1 and addendum 1 files are unchanged and in their own zips; the frozen parameter files and the price book are covered by the record's hashes.
- **The frozen code:** the rest of the frozen code is in the repository at tag `build-freeze` and is pinned file by file by the record.
- **Data:** the confirmatory pool, its labels, captures and campaign data are data, not protocol.
- **Secrets:** the HMAC secret and the Ed25519 private key are never deposited.

## 5. How to check it

1. Each file in the zip is byte-identical to the same path at the tagged commit (`git show osf-deposit-2:<path>`).
2. At tag `build-freeze`: `poetry run python bin/build_freeze.py --verify` recomputes the record byte for byte, and `--check` reports the frozen build.
3. `shasum -a 256 docs/research/h_fact_rubric.md` gives the rubric hash in §1; `tests/labelling/test_rubric.py` pins it.
4. `poetry run python bin/log_deviation.py verify-public` checks every entry and the anchor with the public key only.
