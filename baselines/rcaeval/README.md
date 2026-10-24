# RCAEval baseline environments

Isolated environments for the Family B baselines agreed with the chair (deviation entry 36): B1 multi-source BARO, B2 TraceRCA, B3 BARO (metrics only), B4 PDiagnose, B5 multi-source RCD; alternates CIRCA, then CausalRCA. They never share an environment with HELIOS.

| Image | Python | Methods | Dependencies |
|---|---|---|---|
| `helios-baselines-default:2fca61b` | 3.12 | `mmbaro`, `tracerca`, `baro`, `circa`, `causalrca` (PDiagnose needs an adapter, S4.8) | `constraints-default.txt` |
| `helios-baselines-rcd:2fca61b` | 3.8 | `mmrcd`, `rcd` | RCAEval's `requirements_rcd.lock` |

RCAEval is pinned at commit `2fca61b9730a69c21ef72411844735634dbb010f`; both base images are pinned by digest. Changing either, or the constraints file, needs a deviation entry.

```bash
docker build -f baselines/rcaeval/Dockerfile.default -t helios-baselines-default:2fca61b baselines/rcaeval
docker build -f baselines/rcaeval/Dockerfile.rcd -t helios-baselines-rcd:2fca61b baselines/rcaeval
```

Run with `--network none`. Never run a baseline on confirmatory pool data before tag `build-freeze`. Spike results and open items: `docs/tracking/s0_11_lead_time_register.md` §4.
