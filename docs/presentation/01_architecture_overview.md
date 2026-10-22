# HELIOS — System Architecture Overview
**Heuristic Learning for Integrated Observability Systems**
*Akshay Adik · DBA Research Artefact · Golden Gate University*

---

## Five-Layer Execution Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        C1 — VARIANT CONTROL LAYER (VCL)                     │
│   Variant manifest hash · Snapshot registry · Metric integrity gate          │
│   Exclusion ledger · HMAC-chained deviation log · Reconciliation ledger      │
│   Disjointness auditor · Consensus integrity gate                            │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ gates every layer
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  L0  TELEMETRY INGESTION                                                     │
│  OTEL collectors → Parquet recordings (P1 metrics · P2 traces · P3 logs)    │
│  TelemetryWindow schema (frozen) · variant_config_hash stamped at capture   │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  L1  GRAPH CONSTRUCTION — UEG-C (Unified Evidence Graph with Causality)     │
│  build_ueg_c():  structural edges (topology) + call edges (trace-derived)   │
│  prune_graph():  K-hop personalised PageRank (α=0.85) · Pearson pruning     │
│  Output: UEGCSnapshot  content-hash → SnapshotRegistry                     │
│          50–200 nodes · 4 typed edge classes (structural/call/metric/log)   │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ same content-hashed snapshot
                         ┌─────────┼─────────┐
                         ▼         ▼         ▼
┌───────────────┐ ┌─────────────┐ ┌───────────────────────────────────────┐
│ L2  D-PIPE    │ │  G-PIPE     │ │ L-PIPE                                │
│ Statistical   │ │  Graph PPR  │ │ LLM Explanation                       │
│ Anomaly       │ │  (condition-│ │ (Ollama llama3.1:8b · greedy decode)  │
│ Detection     │ │  al on      │ │ PromptRegistry tamper-guard (SHA lock)│
│               │ │  D-pipe     │ │ ResponseHandler: parse · retry        │
│ Stage A–D:    │ │  disagree-  │ │ Output: CoE narrative + ranked list   │
│ parse →       │ │  ment ≥0.20)│ │                                       │
│ score →       │ │             │ │ Flag: l2c_llm / lpipe                 │
│ propagate →   │ │ Re-runs PPR │ │                                       │
│ rank          │ │ seeded from │ └───────────────────────────────────────┘
│               │ │ D-pipe      │
│ Flags: dpipe  │ │ scores      │
│ dpipe_prop.   │ │             │
│               │ │ Flags:      │
│               │ │ gpipe       │
│               │ │ l2b_graph   │
└───────┬───────┘ └──────┬──────┘
        │                │          ↑ all three produce PipelineVerdict
        └────────┬────────┘         (ranked_candidates, hr_at_3, cpr,
                 ▼                   latency_ms, narrative, snapshot_hash)
┌─────────────────────────────────────────────────────────────────────────────┐
│  L3  COORDINATION — CONSENSUS + ROUTING                                     │
│  UniformBordaConsensus: weighted Borda aggregation of pipeline verdicts     │
│  ConsensusIntegrityGate: verifies fusion_algorithm_sha before every write   │
│  PassthroughConsensus: single-pipeline variants (HELIOS-D, HELIOS-G)       │
│  Output: ConsensusVerdict → ranked root-cause list with calibrated score    │
│  Flags: mahc · cbr · router · acp                                           │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  L4  ACTION / LEARNING  [Phase 2 — AIOpsLab confirmatory runs]              │
│  FGSV shadow validator (KS-gated digital twin)                              │
│  HITL gate · ORAR bandit router (LinUCB, frozen at OSF pre-reg)             │
│  ReconciliationLedger: provisional + terminal reward correspondence          │
│  Flags: reconcile                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Governance Planes (orthogonal to layers)

| Plane | Responsibility |
|---|---|
| **Data** | Schema freeze, Parquet ingestion, TelemetryWindow |
| **Reasoning** | D-pipe · G-pipe · L-pipe peer execution |
| **Coordination** | Consensus, routing, verdict aggregation |
| **Learning** | ORAR parameter update, ReconciliationLedger reward |
| **Evaluation** | C1 enforcement — spans all layers; VCL, gates, ledgers |

---

## Ablation Variants (Confirmatory — 8 pre-registered)

| Variant | What is disabled | Primary hypothesis |
|---|---|---|
| HELIOS-Full | — (reference) | A-H1, A-H3 |
| HELIOS-noLLM | L-pipe (l2c_llm=OFF, lpipe=OFF) | A-H1 — LLM necessity |
| HELIOS-noGraph | G-pipe (l2b_graph=OFF, gpipe=OFF) | Exploratory |
| HELIOS-D | LLM + Graph + Consensus + Router | A-H3 — statistical floor |
| HELIOS-G | LLM + Consensus (graph only) | A-H6 — graph-only |
| HELIOS-noConsensus | MAHC → vote-only passthrough | A-H4 — consensus value |
| HELIOS-noRouter | Uniform routing (cbr=uniform) | A-H5 — routing value |
| HELIOS-noStructural | Topology edges removed (ueg_c_structural=OFF) | A-H8 — C2 value |

*Each variant has a unique content-hashed VCLManifest — enforced by CI at every push.*

---

## Key Metrics

| Metric | Measures |
|---|---|
| **HR@3** | Hit-Rate: true root cause in top-3 candidates |
| **CpR** | Cost per Resolution |
| **H_fact / H_struct** | LLM hallucination rates |
| **CoE quality** | Chain-of-Explanation narrative quality |
| **MTTR reduction** | Operational outcome |

**Statistics:** Wilcoxon signed-rank (binding) · Holm–Bonferroni α=0.00625 per hypothesis
**Corpus:** 8 variants × 5 benchmarks × 40 faults × 10 seeds = 16,000 confirmatory runs
