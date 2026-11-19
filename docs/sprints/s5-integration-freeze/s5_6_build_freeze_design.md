# S5.6 Build freeze · design

**Task:** S5.6, row S2-M10-GATE01 · **Status:** draft for the owner, 2026-11-20 · **Data:** none read; the pool stays locked until the last step

## 1. What the freeze does, and why it needs care

The task breakdown asks for two things: a record of the build (commit, image and model digests, parameter hashes, price book, pool manifest, Tier-2 items moved to Stage B), and tag `build-freeze`, after which "VCL blocks any divergence".

Two facts shape the design:

- **The tag is also the key to the pool.** `helios.telemetry.pool_lock.build_frozen()` only asks whether a tag named `build-freeze` exists. Twenty-two modules (scoring, strata, run metrics, the capture reader, analysis, the campaign runner, the API and the build tools) refuse the confirmatory pool until it does. Creating the tag unlocks all of them at once, and a tag is never moved.
- **Nothing yet checks that a pool run uses the frozen build.** `confirmatory_guard` (analysis, T-i) checks the tag, the variant hashes and the scoring and metrics versions. It does not check the code, the frozen parameter files, the prompts or the model. Stage B work continues on `main` after the tag, so a pool run started from `main` in March would silently use code the deposit never saw.

## 2. Proposed design

### F-a The freeze record

A new file `data/frozen/build_freeze.json`, written by a new `bin/build_freeze.py --write` and checked by `--verify`. Contents, every value computed, none typed by hand:

| Part | What | Source |
|---|---|---|
| Frozen paths | SHA-256 of every tracked file under `helios/`, `bin/`, `data/frozen/` (except the record itself), `research/osf/`, `deploy/`, `baselines/`, plus `pyproject.toml` and `poetry.lock`; and one digest over the sorted list | `git ls-files`, file bytes |
| Parameter hashes | SHA-256 of each of the ten frozen parameter files; the router's refit hash and price-book stamp | `data/frozen/*.json` |
| Price book | SHA-256 of `docs/tracking/price_book.md` (price-book-v3, entry 97) | file |
| Model | `llama3.1:8b`, `EXPECTED_MODEL_DIGEST` (entry 58), Protocol A values, worker prompt SHAs | `lpipe_config` |
| Images | Every `@sha256` pin in `deploy/` and `baselines/` (Ollama, Python base, nginx, the two baseline images) | Dockerfiles, compose |
| Variants and versions | The 15 variant hashes, `SCORING_VERSION`, `METRICS_VERSION`, the analysis plan hash | `helios.vcl`, scoring, run metrics |
| Pool manifest | `data/rcaeval/pool_manifest.json`: its file SHA-256 and `manifest_digest`, 240 cases, dataset revision | manifest only; **no label file is read** |
| Stage B moves | The Tier-2 and flag items not in the frozen build, each with its deviation entry (F-c) | this design |

A record cannot hold the SHA of the commit that contains it. So the record holds file digests; the commit SHA goes into the tag message, the deviation entry and deposit 2.

### F-b "VCL blocks any divergence"

A new module `helios/vcl/freeze.py` (helpers outside `variants.py`, which stays untouched) with one check, `require_frozen_build()`:

1. tag `build-freeze` exists;
2. the record verifies: every frozen path in the working tree matches its digest;
3. at run start, the served model digest equals the record's (the existing check, now read from the record).

Where it is called:

- **Pool campaigns** (`bin/helios_campaign.py`) and **pool scoring and analysis** (`score_runs`, `analyse`, `confirmatory_guard`) refuse to start on any mismatch and name the changed files.
- **Run records** gain `build_freeze_digest`; `confirmatory_guard` adds "a run's build digest is not the frozen one".
- **Build and exploratory corpora** are not affected: Stage B keeps working on `main`.

Consequence: phase E runs from a checkout of the tag (`git worktree add ../helios-evidence build-freeze`), never from `main`. A Stage B commit that touches a frozen path makes `main` fail the check for pool runs, which is the intended block.

### F-c Items not in the frozen build (moved to Stage B)

Recorded in the freeze record and the exit report, each with its existing entry: P4 cognitive (`p4_cognitive`, no consumer; noCogni refused; E-H1) and HIS tiers (`his_tier`, no consumer; HIS3 refused; E-H9), entry 90; `sampling_regime_tag` (no variant), entry 90; E-H8 (the frozen router does not read the ACP), entries 82 and 83; FGSV full twin, IOL sensitivity beyond the shared detector and NER redaction (lite versions frozen), entry 89 and the S4 exit report. No new item is moved by this design.

### F-d The chair call

The owner decided on 2026-11-20 not to wait for the chair call. The S5 plan listed it as a freeze input, so this is recorded in the freeze deviation entry and the exit report. The call topics (CpR and A-H5, the cell rule, the baselines' injection time, the S5 reporting rules) are frozen as deposited in addendum 1. Feedback after the freeze changes nothing silently: it becomes a deviation entry with rerun or exclusion, or a reported limitation.

### F-e Order of steps

1. **Code** (`bin/build_freeze.py`, `helios/vcl/freeze.py`, the call sites, tests: a changed frozen file blocks a pool run, an untouched tree passes, build corpora are unaffected, the record never reads a label file). Full gate, PR, merge. No record yet, no tag.
2. **Freeze deviation entry**: text to the owner first. It names the record's digest, the moved items (F-c) and the chair-call decision (F-d).
3. **Record**: `--write` on `main`, commit with the entry and the tracker row (GATE01 IN_PROGRESS in its own commit first), full gate, PR, merge.
4. **Tag** `build-freeze` (annotated) on that merge commit, after the owner's explicit OK, since it is permanent and unlocks the pool. Then `--verify` on a fresh worktree of the tag.
5. Phase E's first-day pool-only checks (span status-code format, rebuilt series; S4 carry-in) follow, from the tag's worktree.

Effort: about one day of code and gate, plus the owner's two approvals (entry text, tag).

## 3. Decisions for the owner

| # | Decision | Proposal | Alternatives |
|---|---|---|---|
| F-a | Freeze record | **File digests of the frozen paths plus the parameter, model, image, variant, version and pool-manifest digests, in `data/frozen/build_freeze.json`** | Commit SHA only (cannot detect a run from a different checkout) |
| F-b | Divergence block | **Pool campaigns, scoring and analysis refuse on any frozen-path mismatch; runs carry `build_freeze_digest`; phase E runs from a worktree of the tag** | Check the tag only, as today |
| F-c | Stage B moves | **The items listed, all already recorded; nothing new moved** | — |
| F-d | Chair call | **Not waited for; recorded in the freeze entry and exit report** | Wait for the call |
| F-e | Order | **Code first, then entry, then record, then the tag on the owner's OK** | — |

## 4. What this changes and what it does not

- **Changes:** pool runs need the frozen build; run records carry one new field; a new frozen file; the pool unlocks at the tag.
- **Does not change:** any hypothesis, metric, test, alpha, Holm rank, variant hash or frozen parameter; build and exploratory runs; Stage B work on `main`.
