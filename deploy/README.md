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
| `console` | Approval console (S4.2): static page, and a same-origin proxy for `/v1/` and `/health` | `front`, published on loopback port 8081 only | none |

The store is not a service. DuckDB is embedded, and the campaign directory is mounted read-only into `api`. The console holds no secrets: each reviewer types an API key, which is kept for that browser session only.

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

## Approval console

Open `http://localhost:8081` and sign in with a key.

- **Operations mode** (any key with no queue): incidents, runs, verdicts with the full chain of evidence, and decision history. A reviewer key can record decisions.
- **Review mode** (a key with a queue): one case at a time, with "case N of M". The case is revealed only once its view token is issued, so the server's `decision_ms` covers exactly the time the case was on screen.

For an RQ4 session, create one blind key per participant. A blind key sees only its assigned cases, never a variant name, and only its own decisions. Then write the queues:

```bash
hc run --rm admin bin/helios_api.py keygen --keys /secrets/api_keys.json --id P01 --role reviewer --blind
cat > deploy/secrets/assignments.json <<'JSON'
{"assignments": {"P01": ["<run id>", "<run id>"]}}
JSON
hc up -d --force-recreate api                    # queues are read at start
```

Each decision records the server's `decision_ms`, the browser's `client_ms`, `client_hidden_ms` (the time the page was hidden) and, on reject, an optional `chosen_service`.

**Simulated HITL** (scripted reviewer over every run that requests a human; its decisions are tagged `simulated`):

```bash
hc run --rm admin bin/helios_api.py keygen --keys /secrets/api_keys.json --id SIM --role reviewer --simulated > sim.key
poetry run python bin/simulate_hitl.py --api http://localhost:8080 --key-file sim.key --key-id SIM --policy accept
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
| `HELIOS_CONSOLE_PORT` | 8081 | Console host port |
| `HELIOS_CONSOLE_BIND` | loopback | Host address the console is published on |
| `HELIOS_API_BIND` | loopback | Host address the port is published on |
| `HELIOS_OLLAMA_URL` | `http://model:11434` | Runner's model server |

**Exposure.** `/health` is unauthenticated and keys travel in a header without TLS. Keep the API on loopback, or put a TLS reverse proxy in front before setting `HELIOS_API_BIND` to a wider address.
