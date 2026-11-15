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
| `Static_result` | Result of the static scan (from S5.2: `python -m helios.vcl.disjointness`, source scan of `helios/`) |
| `Covered_flags` | Flags with exactly one pipeline function gated by them |
| `Uncovered_flags` | Flags declared in VCLFlag but no pipeline function gated yet (expected during stub phase) |
| `Violations` | Flags gating more than one function (always must be zero) |
| `Dynamic_result` | Until S5.2: coverage.py context labels; from S5.2: the S5.1 per-variant output checks (one observable output per OFF flag) |
| `Notes` | Context / explanation |

**Terminology (S5.2, 2026-11-15; replaces the May definitions, recorded change from schema v1):**
- **Gated region:** every runtime location in `helios/` (outside `helios/vcl/`) that reads a flag: `VCLFlag.X` (`@gated_by` included) or an attribute read on a manifest. A region may span several functions.
- **Covered:** the flag's region is non-empty.
- **No-consumer (declared):** the flag gates nothing in the Stage A build and is listed in `NO_CONSUMER`; the schedule refuses variants that differ from HELIOS-Full only in such flags.
- **Interaction (declared):** a place where two flags combine (one statement or condition, a block guarded by another flag, a `@gated_by` body, or a boolean alias), listed in `INTERACTIONS` with its reason.
- **Violation:** a `@gated_by` entry point with two flags, an undeclared combination, a stale declaration, a flag with no reader that is not declared no-consumer, or a declared no-consumer flag that is read. Any violation fails the audit.
- Until 2026-11-15: *Covered* meant exactly one `@gated_by` function in five pipeline modules, and a flag gating several functions was a violation (design `docs/sprints/s5-integration-freeze/s5_2_disjointness_design.md` §2).

---

## Entries

| Date | SHA | Trigger | Static_result | Covered_flags | Uncovered_flags | Violations | Dynamic_result | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-05-14 | 72f0245 | Milestone 1 gate | PASSED | dpipe, gpipe, lpipe (3) | l2c_llm, p4_cognitive, mahc, cbr, l2b_graph, acp, reconcile, ueg_c_structural, dpipe_propagation, router (10) | 0 | PASSED — HELIOS-Full vs HELIOS-noGraph contexts show disjoint coverage on pipeline stubs | 10 uncovered flags expected; pipeline stubs only gate 3 flags; target is all 13 covered at Stage 5 |
| 2026-05-19 | 0726b59 | Milestone 3 gate | PASSED | gpipe (run_gpipe), dpipe (run_dpipe), l2c_llm (run_lpipe) (3) | mahc, ueg_c_structural, lpipe, cbr, dpipe_propagation, l2b_graph, p4_cognitive, acp, router, reconcile (10) | 0 | PASSED — static scan; dynamic coverage not re-run (no new variant contexts added at M3) | Note: covered set changed from {dpipe, gpipe, lpipe} to {gpipe, dpipe, l2c_llm} — L-pipe full implementation now gated by VCLFlag.L2C_LLM (not VCLFlag.LPIPE); `lpipe` flag moved to uncovered; 10 uncovered flags unchanged; target is all 13 covered at Stage 5 |
| 2026-05-21 | c0b0065 | Milestone 4 architectural review | PASSED | gpipe (run_gpipe), dpipe (run_dpipe), l2c_llm (run_lpipe), l2b_graph (build_ueg_c), mahc (UniformBordaConsensus.fuse) (5) | acp, cbr, router, ueg_c_structural, p4_cognitive, reconcile, dpipe_propagation, lpipe (8) | 0 | PASSED — static scan; DisjointnessAuditor extended to scan class methods via inspect.isclass(); helios.graph.ueg_c_builder and helios.consensus.uniform_borda added to _PIPELINE_MODULES | Coverage increased from 3 → 5: l2b_graph (build_ueg_c) and mahc (UniformBordaConsensus.fuse) now detected; auditor class-method scanning required because @gated_by on an instance method copies __gated_by__ to wrapper via functools.wraps.__dict__ update |
| 2026-11-15 | 1ea6272 | S5.2 certification (row S2-M10-EVAL02) | PASSED | 13: dpipe, gpipe, l2c_llm, l2b_graph, ueg_structural, dpipe_propagation, mahc_hierarchical, cbr_routing, acp_stateful, reconcile_terminal, coe_narrative, fgsv_ks_gate, iol_self_telemetry | None undeclared; declared no-consumer (3): p4_cognitive, his_tier, sampling_regime_tag | 0 (9 declared interaction rows in 6 flag sets: gpipe+l2b_graph, coe_narrative+l2c_llm, cbr_routing+mahc_hierarchical, cbr_routing+gpipe+l2b_graph, cbr_routing+l2c_llm, dpipe+dpipe_propagation) | PASSED: S5.1 per-variant output checks (design D-e), 13 variants, 7,254 runs on OTel v3 and RCAEval build, 0 flag-mark problems ([s5_1_system_test.md](../sprints/s5-integration-freeze/s5_1_system_test.md)) | New definition (design D-a to D-g; deviation entry 90); first run of the source scanner; CI label-only dynamic step removed |

---

## Future Entries

`[PENDING: Stage 2+ — CI appends automatically after each PR via disjointness_audit.yml; manually add a row at each stage gate with the coverage context diff result]`

**Target state at Stage 5 (S5.2):** every boolean flag covered or declared no-consumer; every combination declared; 0 violations. (The May target, "all 13 bool flags covered", predates the 16-flag registry of entry 31 and the three Ch3 flags that have no Stage A consumer.)

---

*Last updated: 2026-11-15 at the S5.2 certification; dynamic result added from S5.1 the same day (4 entries total)*
