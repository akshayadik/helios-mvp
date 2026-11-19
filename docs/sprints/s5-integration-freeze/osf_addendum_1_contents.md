# OSF addendum 1 · contents of the zip

**What:** `osf_addendum_1.zip`, attached to the OSF registration of addendum 1 to KMR3D (DOI 10.17605/OSF.IO/KMR3D). · **Built by:** `git archive` of one commit of this repository, listed paths only, as deposit 1 was (`osf_deposit_1.zip`, deviation entry 37). The commit, the zip's SHA-256 and the addendum's DOI are recorded in the deviation entry that records the deposit, and the commit is tagged `osf-addendum-1`.

## Files

| Path | What |
|---|---|
| `docs/tracking/osf_addendum_draft.md` | The addendum: effect on each pre-registered test, changes by area, frozen files, open items |
| `docs/sprints/s5-integration-freeze/osf_addendum_1_contents.md` | This list |
| `deviation_log.jsonl` | Deviation log, entries 1–99 (HMAC chain; Ed25519 signatures from entry 35). The entries are authoritative where the addendum summarises them |
| `deviation_log.anchor.json` | Signed head anchor: entry count, head signature, SHA-256 of the whole log |
| `docs/tracking/deviation_log.md` | Readable mirror of the log |
| `keys/deviation_log_ed25519.pub.pem` | Public key that verifies every entry and the anchor |
| `data/frozen/*.json` | The ten frozen parameter files of addendum §3 (trigger, D-pipe, G-pipe, MAHC, narrator, router, ACP, τ_N, FGSV lite, IOL lite) |
| `docs/tracking/price_book.md` | Price book v3 (entry 97); its digest is stamped in the frozen router |
| `docs/sprints/s5-integration-freeze/cr01_router_reward_design.md` | CR-01 design note (entry 99), cited in addendum §2.16 |
| `docs/sprints/s5-integration-freeze/cr02_structural_dpipe_design.md` | CR-02 design note (entry 98), cited in addendum §2.16 |
| `docs/sprints/s3-routing/plan.md` | S3 plan, whose addendum bullets this addendum supersedes |
| `docs/tracking/disjointness_audit_log.md` | Flag disjointness audit (entry 90), cited in addendum §2.14 |
| `helios/analysis/reporting.py` | Code of the S5 reporting rules (entries 92–96), cited in addendum §2.15 |

## Not included, and why

- **Deposit 1 files** (`research/osf/`, the metric contract, `helios/research/analysis_plan.py`, `helios/vcl/variants.py`): unchanged since deposit 1 and already in `osf_deposit_1.zip`.
- **The confirmatory pool, captures and campaign data:** the pool stays locked until `build-freeze`; build captures and campaign stores are data, not protocol.
- **Secrets:** the HMAC secret and the Ed25519 private key are never deposited.

## How to check it

1. Each file in the zip is byte-identical to the same path at the tagged commit (`git archive` output, compare with `git show <tag>:<path>`).
2. With the repository at that commit: `bin/log_deviation.py verify-public` checks every entry and the anchor using only the public key.
3. The SHA-256 of each frozen file matches addendum §3.
