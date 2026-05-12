# HELIOS Spine Freeze Memo v0.0

**Version:** v0.0 (Initial Spine Freeze — Stage 0)
**Date:** 2026-05-12
**Status:** Frozen at Stage 0 (VCL Foundation Complete)
**VCL Freeze SHA:** `1278078012207a6d02a9dbe99a9601d9fda48d3f`
**Next Major Freeze Gate:** End of Stage 5 (OSF Full Freeze)
**Repository Location:** `docs/memos/spine_freeze_memo_v0.md` (append-only after v0.0)
**Related Artefacts:**
- `deviation_log.jsonl` (HMAC-SHA256 chained; authoritative) — `docs/tracking/deviation_log.md` is the human-readable companion
- `docs/tracking/HELIOS_MVP_Execution_plan_v0.6.md`
- `docs/osf_protocol_v0.md`
- OSF Protocol Deposit (Stage 0)
- `helios/vcl/` implementation

---

## 1. Purpose of the Spine

This memo defines the **immutable methodological spine** of the HELIOS research artefact (Contribution **C1** — runtime-enforced ablation discipline). It records the exact Variant Control Layer (VCL) configuration, flags, canonical rules, and confirmatory variants that constitute the pre-registered experimental design.

The spine serves as the single source of truth for:
- Deterministic `variant_config_hash` computation
- Runtime gating and disjointness enforcement
- All confirmatory statistical inference (A-H1, A-H3, conditional A-H6)
- C1 descriptive evidence reporting in Chapter 4
- Final OSF deposit and replication package

Any modification to this spine after the respective freeze gates requires a formal deviation entry and re-freeze.

---

## 2. Frozen Elements (Stage 0 Spine)

### 2.1 VCL Flags (14 total — binding)

**Boolean flags (13)** — used for ablation and gating:
- `l2c_llm`, `p4_cognitive`, `mahc`, `cbr`, `l2b_graph`, `acp`, `reconcile`,
  `ueg_c_structural`, `dpipe`, `dpipe_propagation`, `gpipe`, `lpipe`, `router`

**Operational flag (1)**:
- `ingest_mode` ∈ {`"recorded"`, `"live"`} (non-gatable; used directly, never via `@gated_by`)

**Canonical JSON rules for `variant_config_hash`** (immutable — §6.2):
- `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`
- Floats pre-normalised to exactly 6 decimal places before serialisation
- `VCLManifest` uses `ConfigDict(extra="forbid", frozen=True)`
- Hash = SHA-256(canonical JSON bytes, UTF-8)

### 2.2 Confirmatory & Exploratory Variants (8 total) — Full Flag Matrix

**Key:** T = True, F = False. `ingest_mode` = `"recorded"` for all variants.
Column abbreviations: `l2c` = l2c_llm, `p4c` = p4_cognitive, `cbr` = cbr, `l2b` = l2b_graph, `acp` = acp,
`rec` = reconcile, `ueg` = ueg_c_structural, `dpi` = dpipe, `dpp` = dpipe_propagation, `gpi` = gpipe, `lpi` = lpipe, `rtr` = router.

| Variant | l2c | p4c | mahc | cbr | l2b | acp | rec | ueg | dpi | dpp | gpi | lpi | rtr |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| HELIOS-Full | T | T | T | T | T | T | T | T | T | T | T | T | T |
| HELIOS-noLLM | F | T | T | T | T | T | T | T | T | T | T | F | T |
| HELIOS-noGraph | T | T | T | T | F | T | T | T | T | T | F | T | T |
| HELIOS-D | F | T | F | F | F | F | F | T | T | T | F | F | F |
| HELIOS-G | F | T | F | F | T | F | F | T | T | F | T | F | F |
| HELIOS-noConsensus | T | T | F | T | T | T | T | T | T | T | T | T | T |
| HELIOS-noRouter | T | T | T | T | T | T | T | T | T | T | T | T | F |
| HELIOS-noStructural | T | T | T | T | T | T | T | F | T | T | T | T | T |

### 2.3 Variant Identity — Status, Hypothesis, and Frozen Hashes

Hashes computed from `helios/vcl/variants.py` at freeze SHA `1278078`. Any change to flag values invalidates the hash and requires a deviation log entry.

| Variant | Status | Primary Hypothesis | variant_config_hash (SHA-256) |
|---|---|---|---|
| HELIOS-Full | Confirmatory | A-H1, A-H3 baseline | `ca42225f8ed56e1cf2a537dc5a26cd921f5d084da1a6d6f53255ef6ecfcaf8bb` |
| HELIOS-noLLM | Confirmatory | A-H1 | `e4984163d6b42a6371ad3e9fdb90b9943d5e5dfd9b46bdbd9695784884f36e3b` |
| HELIOS-noGraph | Exploratory | — | `aacb1bd99deeb609ac81a3028be74a7b3e76c4e116965521af7f98eb17c0469e` |
| HELIOS-D | Confirmatory | A-H3 | `85fb3b4cf0eb59a8d0251f34392a0c79b1adfa20aa7c7d3544a49e2e8153e3f6` |
| HELIOS-G | Conditional Confirmatory | A-H6 (entry-gate dependent) | `db131257e4e60beac18c4261f9414f1623d3e5bcbbb37e2e0904f66709bac143` |
| HELIOS-noConsensus | Exploratory | A-H4 | `aadf401772414c4f498b438b72ff11f32a5ccd3d5872d4f1c6ed261639a1659e` |
| HELIOS-noRouter | Exploratory | A-H5 | `375802c18a546d9b550540c7858f1682726093004035017be755ba6de752e79e` |
| HELIOS-noStructural | Exploratory | A-H8 | `09c0fe743dc0b7566b52393978e2f39cbc871818f334e3bcbb8710039b28bcd4` |

All 8 hashes are unique (enforced by `tests/test_vcl.py::TestVariants::test_all_variant_hashes_are_unique`).

---

## 3. Research Progress Tracking — C1 Evidence

| Stage | Date | Gate Status | VCL Verification Rate | Snapshot Hash Collisions | Disjointness Audit Status | Exclusion Ledger Entries | Notes |
|---|---|---|---|---|---|---|---|
| 0 | 2026-05-12 | Passed | Baseline established (pre-run) | 0 | Pending (Stage 1 setup) | 0 | VCL core modules frozen; hashes recorded |
| 1 | — | — | — | — | — | — | — |
| 2 | — | — | — | — | — | — | — |
| 3 | — | — | — | — | — | — | — |
| 4 | — | — | — | — | — | — | — |
| 5 | — | — | — | — | — | — | — |

**Pre-registered C1 Targets (§6):**
- VCL verification rate ≥ 99%
- Snapshot-consumption verification = complete (all runs)
- Metric-integrity-gate completion = complete (all runs)
- Final disjointness audit = Pass (static + dynamic)

---

## 4. Deviation Protocol (Binding)

Any change to the frozen spine **must** follow this process:

1. Justify the change against the pre-registered OSF protocol (`docs/osf_protocol_v0.md`).
2. Append a signed entry to `deviation_log.jsonl` via CLI: `poetry run python bin/log_deviation.py --stage ... --clause ... --change ... --reason ... --analytic-consequence ...`
3. Record the deviation reference in this section with timestamp and hash impact.
4. Re-compute and update all affected variant hashes in §2.3.
5. Update OSF deposit if before Stage 5 full freeze.
6. Obtain advisor sign-off and update this table.

| Deviation Ref | Date | Stage | Summary | Hash Impact | Advisor Sign-off |
|---|---|---|---|---|---|
| — | — | — | None (v0.0) | — | — |

---

## 5. Usage Rules (Non-Negotiable)

- This file is **append-only** after initial v0.0. Do not edit existing rows or sections; add only.
- Referenced in every Stage exit report, Chapter 4 draft, and replication README.
- Used by the orchestrator, metric integrity gate, and replication script as ground truth for variant identity.
- Forms the methodological backbone of the final OSF deposit (together with corpus manifest and prompt SHA).
- Serves as the one-page reference during viva defence.

**Approved by Researcher:** Akshay Adik — 2026-05-12
**Advisor Sign-off:** [Pending — to be obtained by end of Stage 0]

---

**Document History**
- v0.0 (2026-05-12): Initial spine freeze at VCL foundation (Stage 0). Flags, canonical rules, all 8 variant hashes, and freeze SHA recorded.

*Successor versions created only via formal deviation + new numbered memo. This file remains the canonical reference.*
