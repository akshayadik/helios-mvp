# VCL Manifest Tracking

**Purpose:** Master register of all Variant Control Layer configurations and the variant_config_hash they produce. Proves binary-level variant identity (Execution Plan §6.1).

**Update cadence:** After every VCL config change or new variant
**Owner module:** Researcher (solo)
**Status:** Stage 0 stub — populate as work progresses.

---

## Hash registry

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
