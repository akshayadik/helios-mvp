# S5.3 refresh: before and after, per directory

Generated from `pilot_cr/before/analysis_<dir>.json` (analysis-v2 on the S5.1 stores) and `pilot_cr/analysis_<dir>.json` (analysis-v2 on the refreshed stores). Family A and B: primary measure, mean per side (HR@3 as a share, log-CpR and log TTCD as means), p-value, and whether it is below its Holm threshold. Per-system rows from `pilot/metrics_<dir>.json` and `pilot_cr/metrics_<dir>.json` (medians). Build data, exploratory.

## otel_build_v3

### Tests

| H | Comparison | mean a/b before | mean a/b after | p before | p after | below thr. before → after |
|---|---|---|---|---|---|---|
| A-H3 | HELIOS-Full vs HELIOS-D | 0.794 / 0.762 | 0.825 / 0.762 | 0.312 | 0.145 | False → False |
| A-H7 | HELIOS-Full vs HELIOS-noLLM | — / — | — / — | — | — | False → False |
| A-H1 | HELIOS-Full vs HELIOS-noLLM | 0.794 / 0.746 | 0.825 / 0.81 | 0.125 | 0.5 | False → False |
| A-H2 | HELIOS-Full vs HELIOS-LLM-only | 0.794 / 0.698 | 0.825 / 0.698 | 0.105 | 0.0287 | False → False |
| A-H6 | HELIOS-Full vs HELIOS-G | 0.767 / 0.721 | 0.814 / 0.721 | 0.312 | 0.0625 | False → False |
| A-H5 | HELIOS-noRouter vs HELIOS-Full | 9.65 / 8.15 | 9.42 / 6.97 | 1.29e-05 | 6.86e-10 | True → True |
| A-H4 | HELIOS-Full vs HELIOS-noConsensus | 0.744 / 0.744 | 0.8 / 0.8 | 0.75 | 0.688 | False → False |
| A-H8 | HELIOS-Full vs HELIOS-noStructural | 0.794 / 0.81 | 0.825 / 0.81 | 0.875 | 0.5 | False → False |
| B-H1 | HELIOS-Full vs BASELINE-1 | 0.794 / 0.54 | 0.825 / 0.54 | 0.000244 | 7.83e-05 | True → True |
| B-H2 | HELIOS-Full vs BASELINE-2 | 0.794 / 0.238 | 0.825 / 0.238 | 1.46e-11 | 3.64e-12 | True → True |
| B-H3 | HELIOS-Full vs BASELINE-3 | 0.794 / 0.302 | 0.825 / 0.302 | 9.71e-09 | 5.38e-10 | True → True |
| B-H4 | HELIOS-Full vs BASELINE-4 | 0.794 / 0.381 | 0.825 / 0.381 | 7.01e-07 | 1.49e-08 | True → True |
| B-H5 | HELIOS-Full vs BASELINE-5 | 0.794 / 0.159 | 0.825 / 0.159 | 5e-12 | 8.02e-12 | True → True |
| B-H7 | BEST-BASELINE vs HELIOS-Full | 9.04 / 8.15 | 9.04 / 6.97 | 0.0378 | 1.04e-06 | False → True |
| B-H6 | BEST-BASELINE vs HELIOS-Full | 4.45 / 3.56 | 4.45 / 2.33 | 0.0554 | 3.91e-06 | False → True |
| B-H8 | HELIOS-Full vs BEST-BASELINE | 0.711 / 0.565 | 0.762 / 0.565 | 0.00189 | 0.000244 | True → True |

### HELIOS systems

| System | HR@1 before → after | HR@3 before → after | median log-CpR before → after | median TTT ms before → after |
|---|---|---|---|---|
| HELIOS-D | 0.302 → 0.302 | 0.762 → 0.762 | 12.03 → 12.03 | 51 → 49 |
| HELIOS-Full | 0.492 → 0.540 | 0.794 → 0.825 | 7.09 → 4.93 | 1434 → 1225 |
| HELIOS-G | 0.508 → 0.508 | 0.762 → 0.762 | 5.04 → 5.00 | 1367 → 1306 |
| HELIOS-LLM-only | 0.492 → 0.492 | 0.698 → 0.698 | 12.03 → 12.03 | 15349 → 15261 |
| HELIOS-noACP | 0.492 → 0.540 | 0.794 → 0.825 | 7.09 → 4.93 | 1301 → 1194 |
| HELIOS-noConsensus | 0.508 → 0.540 | 0.794 → 0.825 | 5.02 → 4.87 | 1319 → 1235 |
| HELIOS-noExpl | 0.492 → 0.540 | 0.794 → 0.825 | 7.09 → 4.91 | 1303 → 1197 |
| HELIOS-noFGSV | 0.492 → 0.540 | 0.794 → 0.825 | 7.09 → 4.92 | 1305 → 1197 |
| HELIOS-noIOL | 0.492 → 0.540 | 0.794 → 0.825 | 7.09 → 4.92 | 1326 → 1194 |
| HELIOS-noLLM | 0.492 → 0.619 | 0.746 → 0.810 | 12.03 → 4.94 | 1349 → 1221 |
| HELIOS-noReconcile | 0.492 → 0.540 | 0.794 → 0.825 | 7.09 → 4.92 | 1321 → 1203 |
| HELIOS-noRouter | 0.492 → 0.540 | 0.794 → 0.825 | 12.03 → 7.42 | 15627 → 15623 |
| HELIOS-noStructural | 0.540 → 0.540 | 0.810 → 0.810 | 7.01 → 7.00 | 475 → 432 |

## rcaeval_build_1

### Tests

| H | Comparison | mean a/b before | mean a/b after | p before | p after | below thr. before → after |
|---|---|---|---|---|---|---|
| A-H3 | HELIOS-Full vs HELIOS-D | 0.964 / 0.933 | 0.97 / 0.933 | 0.0312 | 0.0156 | False → False |
| A-H7 | HELIOS-Full vs HELIOS-noLLM | — / — | — / — | — | — | False → False |
| A-H1 | HELIOS-Full vs HELIOS-noLLM | 0.964 / 0.933 | 0.97 / 0.933 | 0.0312 | 0.0156 | False → False |
| A-H2 | HELIOS-Full vs HELIOS-LLM-only | 0.964 / 0.988 | 0.97 / 0.988 | 0.984 | 0.969 | False → False |
| A-H6 | HELIOS-Full vs HELIOS-G | — / — | — / — | — | — | False → False |
| A-H5 | HELIOS-noRouter vs HELIOS-Full | 7.4 / 5.35 | 7.4 / 4.84 | 6.96e-14 | 1.41e-25 | True → True |
| A-H4 | HELIOS-Full vs HELIOS-noConsensus | 0.909 / 0.955 | 0.947 / 0.974 | 1 | 1 | False → False |
| A-H8 | HELIOS-Full vs HELIOS-noStructural | — / — | — / — | — | — | False → False |
| B-H1 | HELIOS-Full vs BASELINE-1 | 0.964 / 0.897 | 0.97 / 0.897 | 0.00377 | 0.00221 | True → True |
| B-H2 | HELIOS-Full vs BASELINE-2 | — / — | — / — | — | — | False → False |
| B-H3 | HELIOS-Full vs BASELINE-3 | 0.964 / 0.909 | 0.97 / 0.909 | 0.0106 | 0.00636 | True → True |
| B-H4 | HELIOS-Full vs BASELINE-4 | 0.964 / 0.891 | 0.97 / 0.891 | 0.0036 | 0.00129 | True → True |
| B-H5 | HELIOS-Full vs BASELINE-5 | 0.964 / 0.4 | 0.97 / 0.4 | 1.22e-27 | 6.18e-28 | True → True |
| B-H7 | BEST-BASELINE vs HELIOS-Full | 8.2 / 5.47 | 8.2 / 4.93 | 2.05e-16 | 3.99e-18 | True → True |
| B-H6 | BEST-BASELINE vs HELIOS-Full | 3.58 / 0.474 | 3.58 / -0.00889 | 6.83e-17 | 6.01e-21 | True → True |
| B-H8 | HELIOS-Full vs BEST-BASELINE | 0.931 / 0.841 | 0.95 / 0.841 | 3.12e-08 | 6.08e-12 | True → True |

### HELIOS systems

| System | HR@1 before → after | HR@3 before → after | median log-CpR before → after | median TTT ms before → after |
|---|---|---|---|---|
| HELIOS-D | 0.721 → 0.721 | 0.933 → 0.933 | 3.67 → 3.63 | 239 → 213 |
| HELIOS-Full | 0.800 → 0.867 | 0.964 → 0.970 | 3.69 → 3.61 | 234 → 213 |
| HELIOS-G | 0.721 → 0.721 | 0.933 → 0.933 | 3.69 → 3.62 | 237 → 215 |
| HELIOS-LLM-only | 0.842 → 0.842 | 0.988 → 0.988 | 6.83 → 6.83 | 9220 → 9215 |
| HELIOS-noACP | 0.800 → 0.867 | 0.964 → 0.970 | 3.68 → 3.62 | 235 → 226 |
| HELIOS-noConsensus | 0.806 → 0.873 | 0.964 → 0.970 | 3.70 → 3.60 | 239 → 216 |
| HELIOS-noExpl | 0.800 → 0.867 | 0.964 → 0.970 | 3.69 → 3.62 | 242 → 224 |
| HELIOS-noFGSV | 0.800 → 0.867 | 0.964 → 0.970 | 3.69 → 3.62 | 238 → 223 |
| HELIOS-noIOL | 0.800 → 0.867 | 0.964 → 0.970 | 3.69 → 3.61 | 234 → 212 |
| HELIOS-noLLM | 0.721 → 0.721 | 0.933 → 0.933 | 3.70 → 3.63 | 240 → 216 |
| HELIOS-noReconcile | 0.800 → 0.867 | 0.964 → 0.970 | 3.69 → 3.60 | 235 → 220 |
| HELIOS-noRouter | 0.873 → 0.873 | 0.982 → 0.982 | 6.82 → 6.82 | 9220 → 9216 |
| HELIOS-noStructural | 0.800 → 0.867 | 0.964 → 0.970 | 3.69 → 3.59 | 242 → 215 |

## rcaeval_build_2

### Tests

| H | Comparison | mean a/b before | mean a/b after | p before | p after | below thr. before → after |
|---|---|---|---|---|---|---|
| A-H3 | HELIOS-Full vs HELIOS-D | 0.97 / 0.964 | 0.97 / 0.964 | 0.5 | 0.5 | False → False |
| A-H7 | HELIOS-Full vs HELIOS-noLLM | — / — | — / — | — | — | False → False |
| A-H1 | HELIOS-Full vs HELIOS-noLLM | 0.97 / 0.964 | 0.97 / 0.964 | 0.5 | 0.5 | False → False |
| A-H2 | HELIOS-Full vs HELIOS-LLM-only | 0.97 / 0.982 | 0.97 / 0.982 | 1 | 1 | False → False |
| A-H6 | HELIOS-Full vs HELIOS-G | — / — | — / — | — | — | False → False |
| A-H5 | HELIOS-noRouter vs HELIOS-Full | 7.18 / 5.11 | 7.2 / 4.88 | 1.67e-13 | 2.24e-23 | True → True |
| A-H4 | HELIOS-Full vs HELIOS-noConsensus | 0.895 / 0.895 | 0.938 / 0.938 | 1 | 1 | False → False |
| A-H8 | HELIOS-Full vs HELIOS-noStructural | — / — | — / — | — | — | False → False |
| B-H1 | HELIOS-Full vs BASELINE-1 | 0.976 / 0.945 | 0.976 / 0.945 | 0.0547 | 0.0547 | False → False |
| B-H2 | HELIOS-Full vs BASELINE-2 | — / — | — / — | — | — | False → False |
| B-H3 | HELIOS-Full vs BASELINE-3 | 0.976 / 0.933 | 0.976 / 0.933 | 0.0193 | 0.0193 | False → False |
| B-H4 | HELIOS-Full vs BASELINE-4 | 0.97 / 0.812 | 0.97 / 0.812 | 7.45e-09 | 7.45e-09 | True → True |
| B-H5 | HELIOS-Full vs BASELINE-5 | 0.976 / 0.476 | 0.976 / 0.476 | 2.22e-24 | 2.22e-24 | True → True |
| B-H7 | BEST-BASELINE vs HELIOS-Full | 8.01 / 5.15 | 8.01 / 4.93 | 4.01e-21 | 1.01e-21 | True → True |
| B-H6 | BEST-BASELINE vs HELIOS-Full | 3.38 / 0.124 | 3.38 / 0.0746 | 3.7e-22 | 2.12e-21 | True → True |
| B-H8 | HELIOS-Full vs BEST-BASELINE | 0.952 / 0.85 | 0.967 / 0.85 | 2.26e-09 | 1.62e-14 | True → True |

### HELIOS systems

| System | HR@1 before → after | HR@3 before → after | median log-CpR before → after | median TTT ms before → after |
|---|---|---|---|---|
| HELIOS-D | 0.745 → 0.745 | 0.964 → 0.964 | 3.61 → 3.95 | 218 → 321 |
| HELIOS-Full | 0.830 → 0.885 | 0.970 → 0.970 | 3.62 → 3.95 | 219 → 336 |
| HELIOS-G | 0.745 → 0.745 | 0.964 → 0.964 | 3.62 → 3.95 | 217 → 324 |
| HELIOS-LLM-only | 0.879 → 0.879 | 0.982 → 0.982 | 6.81 → 6.83 | 9390 → 9570 |
| HELIOS-noACP | 0.830 → 0.885 | 0.970 → 0.970 | 3.61 → 3.90 | 213 → 298 |
| HELIOS-noConsensus | 0.830 → 0.891 | 0.970 → 0.970 | 3.60 → 3.90 | 211 → 321 |
| HELIOS-noExpl | 0.830 → 0.885 | 0.970 → 0.970 | 3.61 → 3.86 | 214 → 296 |
| HELIOS-noFGSV | 0.830 → 0.885 | 0.970 → 0.970 | 3.59 → 3.91 | 209 → 322 |
| HELIOS-noIOL | 0.830 → 0.885 | 0.970 → 0.970 | 3.61 → 3.84 | 217 → 269 |
| HELIOS-noLLM | 0.745 → 0.745 | 0.964 → 0.964 | 3.63 → 3.94 | 220 → 313 |
| HELIOS-noReconcile | 0.830 → 0.885 | 0.970 → 0.970 | 3.62 → 3.88 | 216 → 322 |
| HELIOS-noRouter | 0.915 → 0.915 | 0.982 → 0.982 | 6.79 → 6.81 | 9384 → 9688 |
| HELIOS-noStructural | 0.830 → 0.885 | 0.970 → 0.970 | 3.61 → 3.88 | 221 → 326 |

## rcaeval_build_3

### Tests

| H | Comparison | mean a/b before | mean a/b after | p before | p after | below thr. before → after |
|---|---|---|---|---|---|---|
| A-H3 | HELIOS-Full vs HELIOS-D | 0.964 / 0.939 | 0.964 / 0.939 | 0.0625 | 0.0625 | False → False |
| A-H7 | HELIOS-Full vs HELIOS-noLLM | — / — | — / — | — | — | False → False |
| A-H1 | HELIOS-Full vs HELIOS-noLLM | 0.964 / 0.939 | 0.964 / 0.939 | 0.0625 | 0.0625 | False → False |
| A-H2 | HELIOS-Full vs HELIOS-LLM-only | 0.964 / 0.939 | 0.964 / 0.939 | 0.109 | 0.109 | False → False |
| A-H6 | HELIOS-Full vs HELIOS-G | — / — | — / — | — | — | False → False |
| A-H5 | HELIOS-noRouter vs HELIOS-Full | 7.31 / 4.99 | 7.31 / 4.72 | 7.88e-20 | 1.94e-29 | True → True |
| A-H4 | HELIOS-Full vs HELIOS-noConsensus | 0.857 / 0.857 | 0.897 / 0.897 | 1 | 1 | False → False |
| A-H8 | HELIOS-Full vs HELIOS-noStructural | — / — | — / — | — | — | False → False |
| B-H1 | HELIOS-Full vs BASELINE-1 | 0.963 / 0.915 | 0.963 / 0.915 | 0.0112 | 0.0112 | True → True |
| B-H2 | HELIOS-Full vs BASELINE-2 | — / — | — / — | — | — | False → False |
| B-H3 | HELIOS-Full vs BASELINE-3 | 0.963 / 0.921 | 0.963 / 0.921 | 0.0193 | 0.0193 | True → True |
| B-H4 | HELIOS-Full vs BASELINE-4 | 0.964 / 0.855 | 0.964 / 0.855 | 0.000155 | 0.000155 | True → True |
| B-H5 | HELIOS-Full vs BASELINE-5 | 0.963 / 0.372 | 0.963 / 0.372 | 9.25e-27 | 9.25e-27 | True → True |
| B-H7 | BEST-BASELINE vs HELIOS-Full | 7.7 / 4.94 | 7.7 / 4.67 | 3.88e-16 | 1.28e-17 | True → True |
| B-H6 | BEST-BASELINE vs HELIOS-Full | 3.06 / -0.102 | 3.06 / -0.259 | 2.7e-17 | 8.12e-18 | True → True |
| B-H8 | HELIOS-Full vs BEST-BASELINE | 0.946 / 0.857 | 0.954 / 0.857 | 1.76e-08 | 2.02e-09 | True → True |

### HELIOS systems

| System | HR@1 before → after | HR@3 before → after | median log-CpR before → after | median TTT ms before → after |
|---|---|---|---|---|
| HELIOS-D | 0.752 → 0.752 | 0.939 → 0.939 | 3.60 → 3.65 | 202 → 216 |
| HELIOS-Full | 0.867 → 0.903 | 0.964 → 0.964 | 3.60 → 3.62 | 207 → 221 |
| HELIOS-G | 0.752 → 0.752 | 0.939 → 0.939 | 3.60 → 3.66 | 209 → 220 |
| HELIOS-LLM-only | 0.836 → 0.836 | 0.939 → 0.939 | 6.79 → 6.79 | 8920 → 8952 |
| HELIOS-noACP | 0.867 → 0.903 | 0.964 → 0.964 | 3.62 → 3.62 | 212 → 228 |
| HELIOS-noConsensus | 0.855 → 0.879 | 0.964 → 0.964 | 3.60 → 3.62 | 205 → 221 |
| HELIOS-noExpl | 0.867 → 0.903 | 0.964 → 0.964 | 3.60 → 3.63 | 202 → 219 |
| HELIOS-noFGSV | 0.867 → 0.903 | 0.964 → 0.964 | 3.60 → 3.62 | 201 → 224 |
| HELIOS-noIOL | 0.867 → 0.903 | 0.964 → 0.964 | 3.61 → 3.62 | 214 → 228 |
| HELIOS-noLLM | 0.752 → 0.752 | 0.939 → 0.939 | 3.60 → 3.66 | 209 → 220 |
| HELIOS-noReconcile | 0.867 → 0.903 | 0.964 → 0.964 | 3.59 → 3.62 | 204 → 221 |
| HELIOS-noRouter | 0.891 → 0.891 | 0.958 → 0.958 | 6.77 → 6.77 | 8929 → 8953 |
| HELIOS-noStructural | 0.867 → 0.903 | 0.964 → 0.964 | 3.60 → 3.62 | 205 → 220 |
