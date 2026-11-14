# HELIOS compose deployment

S4.3, design `docs/sprints/s4-product-eval-tooling/s4_3_compose_design.md`. A fresh install needs Docker with Compose v2.24 or later and a clone of this repository. No Python or Poetry is needed on the host.

All commands run from the repository root. They use this shorthand:

```bash
export HELIOS_REVISION=$(git rev-parse HEAD)   # image tag and ledger commit
alias hc='docker compose -f deploy/compose.yaml'
```

## Services

| Service | What | Network | Secrets |
|---|---|---|---|
| `api` | Read-only verdicts, CoE and decisions over one campaign (S4.1) | `front`, published on loopback port 8080 only | `deploy/secrets/api.env`, `deploy/secrets/api_keys.json` |
| `model-init` | Pulls `llama3.1:8b` into the `ollama` volume, then exits | `egress` (internet, to pull) | none |
| `model` | Ollama | `internal` (no internet, no published port) | none |
| `model-check` | Exits non-zero unless the served digest equals `EXPECTED_MODEL_DIGEST` (entry 58) | `internal` | none |
| `runner` | Runs campaigns (profile `run`) | `internal` | `.env` (deviation-log secrets) |
| `admin` | Creates the decisions secret and API keys (profile `admin`) | none | writes `deploy/secrets/` |

The store is not a service. DuckDB is embedded, and the campaign directory is mounted read-only into `api`. The approval console (S4.2) joins this file later.

## First install

```bash
hc build                                         # HELIOS image from poetry.lock (hash-checked)
mkdir -p deploy/secrets deploy/decisions deploy/runs
hc run --rm admin bin/helios_api.py secret > deploy/secrets/api.env
chmod 600 deploy/secrets/api.env
hc run --rm admin bin/helios_api.py keygen --keys /secrets/api_keys.json --id R1 --role reviewer
#   the key is printed once; only its SHA-256 digest is stored
HELIOS_CAMPAIGN=/path/to/campaign hc up -d       # api, model-init, model, model-check
hc ps                                            # api healthy, model-check exited 0
```

- The first `up` downloads the model (about 4.9 GB). Until `model-init` finishes, `model` does not start.
- On a Linux host, `deploy/secrets` and `deploy/decisions` must be writable by uid 10001, the image's user.

## Check it

```bash
curl -s http://localhost:8080/health             # status, CoE verification, build-freeze
curl -s -H "X-API-Key: $KEY" http://localhost:8080/v1/incidents
hc logs model-check                              # "digest ... matches entry 58"
```

The decisions ledger is written to `deploy/decisions/` (or `HELIOS_DECISIONS`). Verify it on a host with the repository's Python environment:

```bash
set -a; . deploy/secrets/api.env; set +a
poetry run python bin/verify_ledgers.py --decisions deploy/decisions/decisions.jsonl
```

## Runs

The runner reads `data/` read-only and writes to `deploy/runs/` (or `HELIOS_RUN_DIR`). It is the only service given `.env`, so the API never holds the deviation-log secrets.

```bash
hc --profile run run --rm runner bin/helios_campaign.py plan --dir /campaign \
    --manifest data/otel/build_v3_manifest.json --gt-corpus otel_build_v3 \
    --captures data/otel/build_v3
hc --profile run run --rm runner bin/helios_campaign.py run --dir /campaign \
    --phase confirmatory --limit 1
```

- Baseline phases need Docker inside the runner, so they stay on the host.
- **Evaluation runs use the host model server.** Docker on macOS has no GPU access, so the `model` service runs on CPU. It is also a different backend from the one the build data was calibrated on, and greedy decoding can produce different tokens. To point the runner at the host Ollama instead:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.host-model.yaml \
    --profile run run --rm runner bin/helios_campaign.py ...
```

The run-start digest check applies either way.

- The confirmatory pool stays locked inside the image. It has no git, so the `build-freeze` tag check fails closed.

## Settings

| Variable | Default | What |
|---|---|---|
| `HELIOS_CAMPAIGN` | `deploy/campaign` | Campaign directory the API serves (read-only) |
| `HELIOS_DECISIONS` | `deploy/decisions` | Decisions ledger directory |
| `HELIOS_SECRETS` | `deploy/secrets` | `api.env` and `api_keys.json` |
| `HELIOS_RUN_DIR` | `deploy/runs` | Runner campaign directory |
| `HELIOS_API_PORT` | 8080 | Host port |
| `HELIOS_API_BIND` | loopback | Host address the port is published on |
| `HELIOS_OLLAMA_URL` | `http://model:11434` | Runner's model server |

**Exposure.** `/health` is unauthenticated and keys travel in a header without TLS. Keep the API on loopback, or put a TLS reverse proxy in front before setting `HELIOS_API_BIND` to a wider address.
