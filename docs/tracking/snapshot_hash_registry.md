# Snapshot Hash Registry

**Purpose:** Human-readable audit log of every registered `snapshot_hash` with its incident identity, `variant_config_hash`, and registration timestamp. Proves snapshot identity across variants and recording sessions (Execution Plan §6.2).

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** After every recording / replay session
**Owner:** AA
**Authoritative source:** `data/snapshot_registry.jsonl` (populated by `SnapshotRegistry.register()` at runtime)
**Verify command:** `poetry run python bin/verify_captures.py`

---

## Column Definitions

| Column | Meaning |
|---|---|
| `#` | Registry entry number (insertion order) |
| `incident_id` | Fault event identifier |
| `evaluation_phase` | `exploratory` or `confirmatory` |
| `snapshot_hash[:16]` | First 16 hex chars of SHA-256 of `TelemetryWindow` canonical JSON |
| `variant_config_hash[:12]` | First 12 hex chars of the `VCLManifest` hash active at capture time |
| `registered_at` | UTC date of registry entry |

**Two-environment firewall:** All `exploratory` rows are permanently excluded from confirmatory analysis. This is enforced by `EvaluationPhase` in `TelemetryWindow` and checked by `MetricIntegrityGate`.

---

## Entries

All 20 OTEL Demo incidents — captured and processed under **HELIOS-Full** (`variant_config_hash` prefix `20ab0977d268`). All `evaluation_phase = exploratory`.

| # | incident_id | evaluation_phase | snapshot_hash[:16] | variant_config_hash[:12] | registered_at |
|---|---|---|---|---|---|
| 1 | s0-adhc-001 | exploratory | 7e5ffdd5ebc5510f | 20ab0977d268 | 2026-05-14 |
| 2 | s0-adhc-002 | exploratory | 91b74695095c132a | 20ab0977d268 | 2026-05-15 |
| 3 | s0-adhc-003 | exploratory | 8fb867a7ac6e43cf | 20ab0977d268 | 2026-05-15 |
| 4 | s0-cart-001 | exploratory | 5a1d53817b5542d6 | 20ab0977d268 | 2026-05-14 |
| 5 | s0-cart-002 | exploratory | 51c4f4b4cde7ae3c | 20ab0977d268 | 2026-05-15 |
| 6 | s0-cart-003 | exploratory | d2d4bbc73f76a2c4 | 20ab0977d268 | 2026-05-15 |
| 7 | s0-imgsl-001 | exploratory | cc1e726e1024dbc8 | 20ab0977d268 | 2026-05-14 |
| 8 | s0-imgsl-002 | exploratory | 04a7b53e218cb4bf | 20ab0977d268 | 2026-05-15 |
| 9 | s0-imgsl-003 | exploratory | 8d2c547692304ef7 | 20ab0977d268 | 2026-05-15 |
| 10 | s0-imgsl-004 | exploratory | 8685ca711b2eafd3 | 20ab0977d268 | 2026-05-15 |
| 11 | s0-pcat-001 | exploratory | 6b7125a19dcd75cf | 20ab0977d268 | 2026-05-14 |
| 12 | s0-pcat-002 | exploratory | d28d60681bafb7df | 20ab0977d268 | 2026-05-15 |
| 13 | s0-pcat-003 | exploratory | 169aeabafb3945b9 | 20ab0977d268 | 2026-05-15 |
| 14 | s0-pcat-004 | exploratory | 7b38ba83556d448a | 20ab0977d268 | 2026-05-15 |
| 15 | s0-pcat-005 | exploratory | 3ac59f9784bdf989 | 20ab0977d268 | 2026-05-15 |
| 16 | s0-rcf-001 | exploratory | 1dd8b6387ab92eb8 | 20ab0977d268 | 2026-05-14 |
| 17 | s0-rcf-002 | exploratory | 0f84c0bdf55a76d3 | 20ab0977d268 | 2026-05-15 |
| 18 | s0-rcf-003 | exploratory | 5503f04cc0c8e252 | 20ab0977d268 | 2026-05-15 |
| 19 | s0-rcf-004 | exploratory | 24e8b888daa4dba5 | 20ab0977d268 | 2026-05-15 |
| 20 | s0-rcf-005 | exploratory | 604dbfd5966be8c6 | 20ab0977d268 | 2026-05-15 |

**Full `variant_config_hash` for HELIOS-Full:** `20ab0977d268d0441364f39380cd62b5de94d030a0a70f3c68ec04eaa27db472`

---

## Future Entries

`[PENDING: Stage 2 — AIOpsLab confirmatory incidents; evaluation_phase=confirmatory; variant_config_hash will vary by ablation variant (8 confirmatory variants); 174 incidents × up to 8 variants = up to 1392 registry entries]`

---

*Last updated: 2026-05-15 — 20 entries from Milestone 1 corpus run (data/snapshot_registry.jsonl)*
