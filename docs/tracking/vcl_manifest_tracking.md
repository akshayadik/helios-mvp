# VCL Manifest Tracking

**Purpose:** Master register of all Variant Control Layer configurations and the variant_config_hash they produce. Proves binary-level variant identity (Execution Plan §6.1).

**Update cadence:** After every VCL config change or new variant
**Owner module:** Researcher (solo)
**Status:** Current registry: § Registry after S0.4–S0.5 (15 variants, 2026-10-23). Earlier sections are kept as history.

---

## Hash registry (May 2026, superseded)

*Superseded by § Registry after S0.4–S0.5: the flag registry was renamed to the Chapter 3 names and the variants rebuilt (deviation entry 31). Kept as history.*

Hashes computed at commit `573c82f` (post-PR #12 merge). All variants share
`model_version="helios-llm-baseline"`, `prompt_template_id="baseline-v1"`,
`ingest_mode="recorded"`.

| Variant | variant_config_hash | Distinguishing flags (vs Full) |
|---|---|---|
| HELIOS-Full | `20ab0977d268d0441364f39380cd62b5de94d030a0a70f3c68ec04eaa27db472` | All 12 proposal flags + router = True |
| HELIOS-noLLM | `84b80788261fb97b562edeae9bddb06fb53c4c18d88df9c1c505e7e12aa87bdc` | `l2c_llm=False`, `lpipe=False` |
| HELIOS-noGraph | `beb9869d764a2edce8cd7c938cde375f0cdfdcebd249c7a39f9b2110ca08aaca` | `l2b_graph=False`, `gpipe=False` |
| HELIOS-noConsensus | `5e95946bd5d5be76271082c840a500403379762d5da621fac68fd2202b95e9fb` | `mahc=False` |
| HELIOS-noRouter | `1ab2b9c0888841ce7fd759032dd78e7acb76a3f9b89f2bcb3c9c1d225bfa87c0` | `router=False` |
| HELIOS-noStructural | `f13360dcaa47132086b94bd743ce1ad90a75dc23e90a9a29356dd64dce7016d0` | `ueg_c_structural=False` |
| HELIOS-D | `615bdbb7f18dc963da8e1348e4927c2f766e92e8f49032d6f9fe5dfea67599a7` | Statistical-only: `dpipe+dpipe_propagation+ueg_c_structural`; `router=False` |
| HELIOS-G | `7a0df90d85909a58480b1331ba3f703f01c98d52e0822231e7d45ba515681b0a` | Graph-only: `l2b_graph+gpipe+dpipe+ueg_c_structural`; `router=False` |

## Hash computation notes

- Hash = SHA-256 of `canonical_json(manifest.model_dump())`
- `canonical_json` sorts keys, rounds floats to 6 decimal places, no whitespace
- Adding or renaming any `VCLManifest` field invalidates all hashes — requires a deviation log entry
- The `model_` prefix namespace warning is suppressed via `protected_namespaces=()` in `ConfigDict` (Pydantic v2.9)

## Milestone 3 OSF Freeze Verification (2026-05-19)

All 8 variant hashes above were independently verified by `bin/verify_osf_freeze.py --generate` against `research/osf/variant_hashes.json`.

| Freeze artefact | Value |
|---|---|
| `research/osf/variant_hashes.json` | Generated 2026-05-19T03:53:06 UTC |
| VCL freeze SHA (in artefact) | `0233165e891ca860683190eef18873216e14cf32` |
| manifest_sig.txt (over all 6 OSF artefacts) | `e93b5b88339809cdaea7316e5b8f938138f6eb20a227133cda50ef8580ceeb01` |
| CI verification job | `osf-freeze-verify` — runs `--verify` on every push |

All 8 hashes in the registry above are confirmed identical to the frozen OSF artefact. No hash changes since `573c82f`.

## Registry after S0.4–S0.5 (2026-10-23, deviation entry 31)

17 flags (16 boolean + `ingest_mode`), 15 variants: 8 confirmatory (Ch3 Table 17) and 7 exploratory (Ch3 p.153, each HELIOS-Full with one flag OFF). Every variant is built from HELIOS-Full's flags with `_full_except(...)` in `helios/vcl/variants.py`. Hashes recomputed from the code on 2026-10-24; the 8 confirmatory hashes are identical to `research/osf/variant_hashes.json` in OSF deposit 1 (VCL freeze SHA `21944caef2612033de8d196c435e617fb57f9498`, DOI 10.17605/OSF.IO/KMR3D). Uniqueness of all 15 is enforced by `test_all_fifteen_variant_hashes_are_unique`.

| Variant | Status | variant_config_hash | Flags OFF vs HELIOS-Full | Matches deposit 1 |
|---|---|---|---|---|
| HELIOS-Full | confirmatory | `5382fafae6db0a7c6cdbdfb53bfc544ebfcfe707785a78294fea689d28160497` | — (all on) | yes |
| HELIOS-noLLM | confirmatory | `7f82c31138c78b3d696d175d1acb5ad5ce7757dbe8afc788d09c77ad06fdf681` | `l2c_llm` | yes |
| HELIOS-LLM-only | confirmatory | `b16c8aa62dfa253e31b26c2786a2bee73a6280b38c6cc293a5e115b34209680a` | `dpipe_propagation`, `acp_stateful`, `cbr_routing`, `gpipe`, `reconcile_terminal`, `l2b_graph`, `mahc_hierarchical`, `dpipe` | yes |
| HELIOS-D | confirmatory | `794a1bab0b827ce5d436c71f1fb878456000d32545788e97fce38186bcfc0bea` | `acp_stateful`, `cbr_routing`, `gpipe`, `l2c_llm`, `reconcile_terminal`, `l2b_graph`, `mahc_hierarchical` | yes |
| HELIOS-noConsensus | confirmatory | `40360d2e8e841d52c850daeb70943ee4559cb55c9ca508129f2c70f5b74de1b4` | `mahc_hierarchical` | yes |
| HELIOS-noRouter | confirmatory | `69a0ed936c929c616b1af70e2b3dc19e07be97e70607eab27113e738f784b358` | `cbr_routing` | yes |
| HELIOS-G | confirmatory | `7b3c08e169c2e5a6e9274205aaf34edb0cc0dc8fa485780a4dc161f3f5bf9975` | `dpipe_propagation`, `acp_stateful`, `cbr_routing`, `l2c_llm`, `reconcile_terminal`, `mahc_hierarchical` | yes |
| HELIOS-noStructural | confirmatory | `a6a64740c3150ae9b7e823e50d8f44307f9ef3c9a35c1f5151da573e35f410a7` | `ueg_structural` | yes |
| HELIOS-noCogni | exploratory | `77393185f21c62f16ef720e09db44d378d909a711eec2a22857e37e346779c72` | `p4_cognitive` | n/a (exploratory) |
| HELIOS-noACP | exploratory | `2f4866e6e670419e13f56d311f3507ae6cb64efa14b00e2dd4234e916a67a0b6` | `acp_stateful` | n/a (exploratory) |
| HELIOS-noReconcile | exploratory | `003940202112a3a50d83a34b14a31e2ed3c65f168a6752b57450c9a1d6c97d89` | `reconcile_terminal` | n/a (exploratory) |
| HELIOS-HIS3 | exploratory | `b6f325139863755de9c33be797fbbe2cc5bc2c746f921a64df151d132dfe768f` | `his_tier` | n/a (exploratory) |
| HELIOS-noFGSV | exploratory | `4b7d1c9aa21f78efa6b3ebf7a88acbc4cf3f799564c6218921b855f4634ac5d9` | `fgsv_ks_gate` | n/a (exploratory) |
| HELIOS-noIOL | exploratory | `af55fe7c01817a4259123097c4b4bbc35edabb95afcaa0ef29ca0ce542bc89a1` | `iol_self_telemetry` | n/a (exploratory) |
| HELIOS-noExpl | exploratory | `e65e0d47a54e77741d8d996478320c0fff7d47db1f9b2ed8a1b53b794b1734b2` | `coe_narrative` | n/a (exploratory) |

*Recorded late:* this table should have been added with S0.4–S0.5 (PR #43); it was added during the S0 documentation sync (2026-10-24).
