# S5.2 Disjointness certification · design

**Row:** S2-M10-EVAL02 · **Status:** approved by the owner 2026-11-15 (D-a to D-g as written) · **Plan:** [plan.md](plan.md) § Found during this refresh

## 1. What the certification has to show

Ch3 §3.9.1, Threat 2: switching off one `VCLFlag` must change only the code that flag controls. If it does not, a variant comparison measures more than the one mechanism it is named after.

The S5.2 done-when reads: "every boolean flag gates exactly one code path; zero uncovered". This design makes that criterion checkable on the code as built.

## 2. Where the current audit falls short

`helios/vcl/disjointness.py` (written in May, for the pipeline stubs) has four gaps.

| Gap | Effect today |
|---|---|
| It scans five hard-coded modules for `@gated_by` only | 11 of the 16 flags show as UNCOVERED, although 8 of them have readers |
| It treats a flag that gates several functions as a **violation** | Scanning the built code would fail the audit on correct designs: `cbr_routing` gates two router functions, `mahc_hierarchical` gates both the uniform Borda fallback and MAHC, and `dpipe` gates both the D-pipe and its stub |
| It never looks for code controlled by two flags at once | That case is the real Threat 2 risk, and nothing checks for it |
| The CI "dynamic" step runs the same test suite twice under two labels (`HELIOS-Full`, `HELIOS-noGraph`) | No manifest changes between the two runs, so the step cannot fail. `HELIOS-noGraph` is also no longer a variant |

`helios/vcl/catalog.py::flag_readers` (S4.10) already parses every file for flag reads, so the schedule can refuse variants whose flags have no reader. It counts `<anything>.<flag>` as a read, so `chain.dpipe` (a parameter set, not the flag) counts too. That is harmless for refusal, but too loose for a certificate.

## 3. Scan of the code as built (2026-11-15, `main` 73e689b)

A flag is counted as read when the code references `VCLFlag.X` (decorators included) or reads an attribute on a manifest (`manifest.x`, `self._manifest.x`). The scan covers runtime code in `helios/`; `helios/vcl/` is excluded.

| Flag | Runtime readers |
|---|---|
| `dpipe` | D-pipe and its stub |
| `gpipe` | G-pipe, runner |
| `l2c_llm` | L-pipe, runner, schedule |
| `l2b_graph` | graph builder, G-pipe, runner |
| `ueg_structural` | structural bundle, G-pipe |
| `dpipe_propagation` | D-pipe |
| `mahc_hierarchical` | MAHC, uniform Borda, runner |
| `cbr_routing` | router, runner |
| `acp_stateful` | runner |
| `reconcile_terminal` | reward replay |
| `coe_narrative` | narrative engine, runner, API reader |
| `fgsv_ks_gate` | runner |
| `iol_self_telemetry` | runner |
| `p4_cognitive`, `his_tier`, `sampling_regime_tag` | **none** |

The scan finds three places where two flags combine on one code path:

| Where | Flags | Why |
|---|---|---|
| runner, G-pipe admission (and the early returns at the top of the G-pipe) | `gpipe` and `l2b_graph` | The G-pipe needs a graph. With `l2b_graph` OFF there is no graph, so the G-pipe cannot run either |
| runner, narrative step (same expression, plus two nested blocks) | `coe_narrative`, then `l2c_llm` | `coe_narrative` decides whether a narrative is written; `l2c_llm` picks the LLM narrator or the template narrator |
| runner, signal typing (through the local variable `routed_run`) | `mahc_hierarchical` or `cbr_routing` | Both MAHC and the router need the signal type |

All three are intended, and each matches how Ch3 Table 17 defines the variants. They still matter for reading results: with `l2b_graph` OFF the G-pipe is off too, so that variant also removes the G-pipe. They therefore have to be stated in the certificate, not discovered by an examiner.

## 4. Proposed design (decisions D-a to D-g)

**D-a Definition.** A flag's *gated region* is every runtime location that reads it. The certificate requires three things:

1. Every flag has a non-empty region, or is on the declared no-consumer list (D-d).
2. No `@gated_by` entry point carries two flags. This is the existing registry check, kept as it is.
3. Every place where two flags combine is in a declared interaction table (D-c).

A region may span several functions. The rule "one flag, one function" is dropped, because it fails on correct designs (§2). The done-when's "exactly one code path" is read as "one gated region per flag, and no undeclared overlap". *Alternative:* keep "one function per flag" and add a decorated wrapper for each flag. That needs no change to the definition, but it means touching gated code in the frozen path (runner, router, MAHC) only to satisfy the audit. I don't recommend it.

**D-b One scanner.** Rewrite `DisjointnessAuditor` as an AST scan over all of `helios/` (outside `helios/vcl/`), with no imports and no fixed module list. A read is `VCLFlag.X`, or an attribute read whose receiver is a manifest (`manifest`, `self._manifest`, `_manifest`). Each read is recorded as file, function and line.

`catalog.flag_readers` then calls the same scanner. The schedule's refusal is unchanged in result: the two variants refused today stay refused, as an existing test already checks. `bin/` build tools are reported in a separate column and do not count as runtime readers.

**D-c Interaction table.** A constant in `helios/vcl/disjointness.py` lists each allowed combination, with its flags, its location and its reason. The three rows of §3 are its starting content.

The scanner fails the audit on any combination missing from the table, where a combination is:

- two flags in one condition or assignment;
- a flag read inside a block guarded by another flag;
- a local variable assigned from a flag read and then used in another flag's condition.

It also fails on a table row that no longer matches the code. A test plants each of the three forms in a temporary tree and expects a failure.

**D-d No-consumer list.** A second constant: `p4_cognitive`, `his_tier`, `sampling_regime_tag`. A test fails in either direction: if one of these gains a reader without being removed from the list, or if any other flag loses its last reader.

A second test ties this list to the schedule: the refused variants are exactly those that differ from HELIOS-Full only in no-consumer flags (today noCogni and HIS3). `sampling_regime_tag` belongs to no variant, so nothing is refused for it.

**D-e Dynamic check moves to S5.1.** Remove the CI step that cannot fail.

- **Decorated paths** are already enforced at run time: `@gated_by` raises `GatedComponentInactiveError` when called under an OFF flag.
- **Manifest-read paths** are checked in S5.1. For each of the 13 runnable variants, the system test checks one observable output per OFF flag:
  - routing mode "uniform";
  - CoE step A `UNVALIDATED` / `fgsv_off`;
  - no step S;
  - no narrative;
  - no G-pipe verdict;
  - no propagation evidence.
- The test also checks that no run raised `GatedComponentInactiveError`.

The CI job keeps the static audit and adds the S5.1 test.

**D-f Records.** `docs/tracking/disjointness_audit_log.md` gains the S5 certification row (static result, readers per flag, the interaction table, the no-consumer list, the S5.1 dynamic result). Its terminology note is updated to the D-a definition, and its old target ("all 13 bool flags covered") is corrected to the Stage A state, recorded as a change from schema v1.0.

**D-g Deviation entry.** Propose one entry at certification. It records:

- the D-a definition, which replaces the May audit's "one function per flag";
- the three declared interactions, with their consequence for reading `l2b_graph` OFF;
- the three Ch3 flags that gate nothing in the frozen build.

No variant, hash, metric or frozen file changes. The entry gives examiners the ablation boundaries before the freeze. I'll bring its text for your approval when the code is done.

## 5. Scope, files, done-when

- **Code:**
  - `helios/vcl/disjointness.py` (scanner, interaction table, no-consumer list, CLI output with readers per flag);
  - `helios/vcl/catalog.py` (`flag_readers` delegates to the scanner);
  - `.github/workflows/disjointness_audit.yml` (static audit plus the S5.1 test).
- **Not touched:**
  - `helios/vcl/variants.py` (read-only, OSF-fingerprinted);
  - every variant hash;
  - the gated code itself (no wrappers added; D-a).
- **Tests** (`tests/test_disjointness.py`):
  - planted reads of each kind;
  - planted undeclared combinations;
  - a stale table row;
  - the no-consumer list in both directions;
  - schedule refusal consistency.

  The existing registry tests stay.
- **Done when:** `python -m helios.vcl.disjointness` reports 13 flags covered, 3 declared no-consumer, 3 declared interactions, 0 violations and 0 undeclared combinations. The full gate is green. The audit-log row is written. The S5.1 per-variant checks are recorded as the dynamic part when S5.1 closes.
- **Effort:** about 1½ days, within the 2 days the plan gives S5.2 (1 plus 1 for the audit extension).

## 6. Implementation result (2026-11-15)

Built as designed in `helios/vcl/disjointness.py`. `catalog.flag_readers` now delegates to the scanner, and `.github/workflows/disjointness_audit.yml` runs the audit and its tests. `python -m helios.vcl.disjointness` reports: **13 covered, 3 declared no-consumer, 9 declared interaction rows, 0 violations.**

**Two refinements made while building, both narrowing what counts as a combination:**

- **Guards.** An exiting `if` counts as a guard only when the flag's state alone decides it: `if not F: return`, or `F` / `not F` as one operand of an `or`. A refusal such as `if F and provisional: raise` decides nothing about the code after it, because that code runs with the flag in either state.
- **Aliases.** Only boolean aliases are followed (`routed_run = manifest.cbr_routing`). A value computed from a flag, such as the narrative the narrator returns, is data flow. It is left to the S5.1 output checks (D-e).

Tests plant each counted form and each excluded form.

**Combinations found: nine sites in six flag sets.** §3 listed three. The full scan, which also covers `@gated_by` bodies and the other runner methods, finds three more intended flag sets: the router's reachable arms (two sets) and D-pipe propagation. A row is a file, a scope and a flag set.

| Flags | Where | Why |
|---|---|---|
| `gpipe` + `l2b_graph` | runner `_process_incident`; G-pipe `should_run_gpipe` | The G-pipe needs a graph |
| `coe_narrative` + `l2c_llm` | runner `_process_incident`, `_trigger_for` (refusal of a provisional narrator prompt), `_parameter_hashes` (narrator prompt hash) | Narrative on/off; LLM or template narrator |
| `cbr_routing` + `mahc_hierarchical` | runner `_process_incident` | Both need the signal type |
| `cbr_routing` + `gpipe` + `l2b_graph` | runner `_process_incident` | **New.** The router decides on the G arm only when the G-pipe can run (reachable arm set, S3.1 R-c) |
| `cbr_routing` + `l2c_llm` | runner `_process_incident` | **New.** The escalation decision knows whether the L-pipe is on (`llm_on`, R-c) |
| `dpipe` + `dpipe_propagation` | D-pipe `run_dpipe` (a `@gated_by(VCLFlag.DPIPE)` body) | **New.** Propagation is a stage inside the D-pipe |

What this means for reading results: noRouter and the arm-removing variants (noLLM, G, D) already differ in the router's reachable set, as S3.1 R-c records. No variant turns off `dpipe` alone while keeping `dpipe_propagation`. The done-when count in §5 is therefore nine declared rows rather than three, and these are the rows the D-g entry will list.
