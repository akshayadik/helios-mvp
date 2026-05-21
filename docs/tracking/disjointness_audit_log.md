# Disjointness Audit Log

**Purpose:** Static + dynamic disjointness audit results for every CI run and stage gate. CI-generated; manually verified at stage gates. Implements §3.9.1 Threat 2 mitigation.

**Schema version:** v1.0 (frozen 2026-05-15)
**Update cadence:** Every PR + every stage gate
**Owner:** AA / CI (`.github/workflows/disjointness_audit.yml`)
**Manual run:** `poetry run python -m helios.vcl.disjointness`

---

## Column Definitions

| Column | Meaning |
|---|---|
| `Date` | Audit run date |
| `SHA` | Git commit SHA at audit time |
| `Trigger` | What caused the audit run |
| `Static_result` | Result of `__gated_by__` attribute scan across pipeline modules |
| `Covered_flags` | Flags with exactly one pipeline function gated by them |
| `Uncovered_flags` | Flags declared in VCLFlag but no pipeline function gated yet (expected during stub phase) |
| `Violations` | Flags gating more than one function (always must be zero) |
| `Dynamic_result` | Coverage.py context diff: HELIOS-Full vs ablation variant |
| `Notes` | Context / explanation |

**Terminology:**
- **Covered:** `VCLFlag.X` has exactly one `@gated_by(VCLFlag.X)` decorated function in pipeline modules
- **Uncovered:** Flag exists in `VCLFlag` but no pipeline function gated yet — normal during stub phase; target is all 13 bool flags covered at Stage 5
- **Violation:** Flag gates more than one function — forbidden, causes audit FAIL

---

## Entries

| Date | SHA | Trigger | Static_result | Covered_flags | Uncovered_flags | Violations | Dynamic_result | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-05-14 | 72f0245 | Milestone 1 gate | PASSED | dpipe, gpipe, lpipe (3) | l2c_llm, p4_cognitive, mahc, cbr, l2b_graph, acp, reconcile, ueg_c_structural, dpipe_propagation, router (10) | 0 | PASSED — HELIOS-Full vs HELIOS-noGraph contexts show disjoint coverage on pipeline stubs | 10 uncovered flags expected; pipeline stubs only gate 3 flags; target is all 13 covered at Stage 5 |
| 2026-05-19 | 0726b59 | Milestone 3 gate | PASSED | gpipe (run_gpipe), dpipe (run_dpipe), l2c_llm (run_lpipe) (3) | mahc, ueg_c_structural, lpipe, cbr, dpipe_propagation, l2b_graph, p4_cognitive, acp, router, reconcile (10) | 0 | PASSED — static scan; dynamic coverage not re-run (no new variant contexts added at M3) | Note: covered set changed from {dpipe, gpipe, lpipe} to {gpipe, dpipe, l2c_llm} — L-pipe full implementation now gated by VCLFlag.L2C_LLM (not VCLFlag.LPIPE); `lpipe` flag moved to uncovered; 10 uncovered flags unchanged; target is all 13 covered at Stage 5 |
| 2026-05-21 | c0b0065 | Milestone 4 architectural review | PASSED | gpipe (run_gpipe), dpipe (run_dpipe), l2c_llm (run_lpipe), l2b_graph (build_ueg_c), mahc (UniformBordaConsensus.fuse) (5) | acp, cbr, router, ueg_c_structural, p4_cognitive, reconcile, dpipe_propagation, lpipe (8) | 0 | PASSED — static scan; DisjointnessAuditor extended to scan class methods via inspect.isclass(); helios.graph.ueg_c_builder and helios.consensus.uniform_borda added to _PIPELINE_MODULES | Coverage increased from 3 → 5: l2b_graph (build_ueg_c) and mahc (UniformBordaConsensus.fuse) now detected; auditor class-method scanning required because @gated_by on an instance method copies __gated_by__ to wrapper via functools.wraps.__dict__ update |

---

## Future Entries

`[PENDING: Stage 2+ — CI appends automatically after each PR via disjointness_audit.yml; manually add a row at each stage gate with the coverage context diff result]`

**Target state at Stage 5:** all 13 bool flags covered, 0 violations.

---

*Last updated: 2026-05-21 at Milestone 4 architectural review (3 entries total)*
