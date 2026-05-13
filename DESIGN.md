# HELIOS Design Documentation

## 1. Project Overview
HELIOS (Hybrid Explainable Learning for Incident Observability and Supervision) is a hybrid multi-pipeline Root Cause Analysis (RCA) framework designed for microservice environments. The MVP focuses on establishing a rigorous, research-grade foundation for evaluating RCA techniques through "Runtime-Enforced Ablation Discipline."

## 2. Core Architecture
The system is built around a "Spine-and-Body" architecture where the immutable spine handles research integrity, and the modular body contains the diagnostic pipelines.

### 2.1 Peer Pipelines
- **D-pipe (Statistical)**: Pearson/Spearman correlation and propagation.
- **G-pipe (Graph)**: Graph-based causal traversal using the UEG-C canonical graph.
- **L-pipe (LLM)**: LLM-assisted explanation and hypothesis generation (Protocol A).

### 2.2 Consensus Layer
The **Uniform Borda consensus layer** fuses per-pipeline ranked candidate lists into a single verdict, ensuring a balanced contribution from all active pipelines.

---

## 3. Key Component: Variant Control Layer (VCL)
The **Variant Control Layer (VCL)** is the most critical component from a design and research perspective. It serves as the "immutable spine" of the project, implementing **Contribution C1: Runtime-Enforced Ablation Discipline**.

### 3.1 Design Importance
In typical AI research, ablation studies (removing components to measure their impact) are often performed post-hoc or through manual configuration, which can lead to "construct validity" issues. VCL addresses this by making ablation a first-class, runtime-enforced citizen of the architecture.

### 3.2 Principles of Operation
- **Single Source of Truth**: All experimental flags are declared in a central `VCLManifest`.
- **Deterministic Identity**: Each variant is uniquely identified by a `variant_config_hash` (SHA-256 of the canonical JSON manifest). This hash is carried through every measurement run.
- **Runtime Enforcement**: A `@gated_by(flag)` decorator ensures that code paths belonging to ablated components are unreachable. Any attempt to invoke an inactive component raises a `GatedComponentInactiveError`.
- **Provable Disjointness**: Static and dynamic audits verify that ablation code paths do not overlap, guaranteeing that the observed performance delta is purely attributable to the toggled flags.

---

## 4. Novelty and Innovation
HELIOS introduces several novel concepts to the field of AIOps and software engineering research:

### 4.1 C1: Runtime-Enforced Ablation Discipline
The primary novelty is the systematic integration of research integrity tools directly into the execution runtime. This includes:
- **HMAC-Chained Deviation Log**: A cryptographically-signed record of every protocol change, preventing silent "p-hacking" or undocumented changes to the experiment.
- **Exclusion Ledger**: A signed record of every run that failed metric integrity gates, ensuring transparency in data exclusion.
- **Snapshot Hashing**: Content-addressable telemetry snapshots (UEG-C) ensure that all pipelines in a variant see the exact same input state.

### 4.2 UEG-C (Unified Event Graph with Cognitive nodes)
A novel canonical graph representation that integrates distributed traces, logs, and metrics into a single causal structure. Its content-hashed identity ensures that graph-based reasoning is deterministic and reproducible.

### 4.3 Two-Environment Firewall
A strict architectural separation between **Exploratory Calibration** (using OTEL Demo) and **Confirmatory Inference** (using AIOpsLab). This "firewall" prevents over-fitting to the calibration set and strengthens the validity of the final research findings.

---

## 5. Design Science Research (DSR) Alignment
The project follows the DSR methodology (Hevner et al., 2004), where the HELIOS artefact itself is the unit of analysis. The design prioritizes:
- **Construct Validity**: Guaranteed by VCL and Disjointness Audits.
- **Internal Validity**: Enforced by Snapshot Hashing and Metric Integrity Gates.
- **Reliability**: Ensured by the HMAC-chained logs and OSF Pre-registration protocol.

---

## 6. References
- **OSF Pre-Registration Protocol**: `docs/osf_protocol_v0.md`
- **Execution Plan**: `docs/tracking/HELIOS_MVP_Execution_plan_v0.6.md`
- **Ablation Architecture**: `docs/tracking/ablation_architecture.md`
- **Research Proposal**: `.claude/docs/pdf/research_proposal_akshayadik.pdf`
- **Project Plan**: `.claude/docs/pdf/project_plan.md`
