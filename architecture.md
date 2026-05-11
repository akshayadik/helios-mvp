# HELIOS System Architecture (Ablation-Aware)

## Design Principles (Section 3.6.2)
1. Pipeline Independence (peer pipelines: D-pipe, G-pipe, L-pipe)
2. Ablation-First Design (feature flags control every C2–C6 contribution)
3. Bounded Reproducibility (single binary + OSF freeze)
4. Separation of Diagnosis from Action
5. Failure-as-Covariate + Self-Telemetry

## Key Components (3.6.3)
- UEG-C (Unified Event Graph with Cognitive nodes)
- Multi-pipeline: Statistical (D), Graph-ML (G), LLM (L), CBR Routing, etc.
- Ablation flags: l2c_llm, p4_cognitive, mahc_hierarchical, etc.
- Observability planes + reconciliation ledger (runtime DSR enforcement)

Reference: Full spec in PDF pages 106–120. Use feature flags for all variants (HELIOS-Full vs noLLM, noStructural, etc.).