# Baseline licences (S4.8, design B-j)

RCAEval is pinned at commit `2fca61b9730a69c21ef72411844735634dbb010f` (MIT License, Copyright (c) 2024 Luan Pham). Each bundled method carries its own licence in RCAEval's `LICENSES/` folder; the table records what the README at that commit states. Read inside `helios-baselines-default:2fca61b` on 2026-11-13.

| Baseline | Role | RCAEval source at 2fca61b | Licence | Image (digest) | Modified by HELIOS |
|---|---|---|---|---|---|
| Multi-source BARO (`mmbaro`) | B1 (B-H1) | `RCAEval/e2e/baro.py` | MIT (`LICENSES/LICENSE-BARO`) | default `sha256:bd05e0dcf6d6…` | No |
| TraceRCA (`tracerca`) | B2 (B-H2) | `RCAEval/e2e/tracerca.py` | RCAEval's MIT (no separate licence listed) | default | No |
| BARO, metrics only (`baro`) | B3 (B-H3) | `RCAEval/e2e/baro.py` | MIT (`LICENSES/LICENSE-BARO`) | default | No |
| PDiagnose | B4 (B-H4) | `RCAEval/e2e/pdiagnose.py` (a script) | RCAEval's MIT (no separate licence listed) | default | **Yes**: ported to a function, `baselines/rcaeval/adapters/pdiagnose_adapter.py`; departures listed there and in the deviation entry |
| Multi-source RCD (`mmrcd`) | B5 (B-H5) | `RCAEval/e2e/mmrcd.py` (with `rcd`, causal-learn) | MIT (`LICENSES/LICENSE-RCD`, `LICENSE-causal-learn`) | rcd `sha256:54c3079b5b48…` | No |
| CIRCA, metrics only (`circa`) | Alternate 1 | `RCAEval/e2e/circa.py` | BSD 3-Clause (`LICENSES/LICENSE-CIRCA`) | default | No |
| CausalRCA (`causalrca`) | Alternate 2 | `RCAEval/e2e/causalrca.py` | **No licence** (README: "No License") | default | No |

Notes:
- CausalRCA has no licence: its use here is limited to running it unmodified for research evaluation, and it is only an alternate. If it ever replaces a baseline, the owner decides on its use before the build freeze.
- HELIOS's own wrapper (`run_method.py`) imports RCAEval inside the container only; no RCAEval code is copied into the HELIOS package. The PDiagnose port is a derivative of RCAEval's MIT-licensed script and keeps that attribution.
- Changing the RCAEval commit, an image or `constraints-default.txt` needs a deviation entry (README).
