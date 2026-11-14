# S4.3 Compose deployment: design (draft)

**Row:** S2-M9-ENG03 · **Effort:** ½ day · **Depends on:** S4.1 (API, PR #95) · **Feeds:** S4.2 (approval console joins the same compose file) · **Status:** approved 2026-11-14 (C-a to C-h as recommended)

## 1. What is fixed already

- **Task** (`helios_task_breakdown.md` S4.3): docker-compose for the API, console, store and model server; images pinned by digest.
- **Done when:** a fresh install works from the compose file alone.
- **e2e plan:** compose is Tier 1 in S4. Helm and production deployment are Stage B (B1).
- **Rules from S4.1 that the deployment must keep:**
  - the API never holds a `DEVIATION_*` secret and refuses to start if one is in its environment;
  - API keys are stored as digests only, in a gitignored key file (`api_keys.json`);
  - the decisions secret lives in a gitignored `.env.api`;
  - the API serves a store that no campaign is writing to, read-only.

## 2. What exists today

| Piece | State |
|---|---|
| API | `bin/helios_api.py serve --campaign DIR --keys FILE`. It binds to loopback by default; `--host` widens it |
| Store | Embedded DuckDB, one file per campaign (`results.duckdb`), plus `coe/` and `decisions/`. There is no database server to deploy |
| Model server | Host Ollama serving `llama3.1:8b`. The run-start check compares the served digest with `EXPECTED_MODEL_DIGEST` (entry 58). The URL is a constant, `OLLAMA_BASE_URL = http://localhost:11434` (`lpipe_config.py`) |
| Runs | `bin/helios_run.py` and `bin/helios_campaign.py`. They need both deviation-log secrets (the CoE signer) |
| Console | Not built yet (S4.2 comes after S4.3 in the S4 plan) |
| Docker | Only the two RCAEval baseline images (`baselines/rcaeval/Dockerfile.*`), with base images pinned by digest |

## 3. Decisions for the owner

### C-a. Services

- **Recommended:** four services in one `deploy/compose.yaml`:

| Service | Image | Holds | Starts by default |
|---|---|---|---|
| `api` | HELIOS image (C-b) | `.env.api`, `api_keys.json`, the campaign directory mounted read-only, the decisions directory mounted read-write | yes |
| `model` | Ollama, pinned by digest | the model weights in a named volume | yes |
| `model-init` | the same Ollama image | runs once: pulls `llama3.1:8b`, then checks the digest (C-d) | yes, then exits |
| `runner` | HELIOS image | `.env` (deviation secrets) and the campaign directory read-write | no: `--profile run`, used as `docker compose run runner ...` |

- **The store is a mounted directory, not a service.** DuckDB is embedded, so "store" means the campaign directory on the host (`HELIOS_CAMPAIGN`), plus a named volume for decisions if no directory is given.
- **Console:** S4.2 adds a `console` service to the same file, and its done-when covers it. S4.3 leaves a commented slot.
- **The runner is separate from the API** so the deviation secrets never enter the API container. It also keeps the S4.1 rule that runs are never started from a web request.
- (b) API and model only, with runs left on the host. Simpler, but then "fresh install" cannot produce a verdict without a host Python environment.

### C-b. HELIOS image

- **Recommended:**
  - `deploy/Dockerfile`, multi-stage, on `python:3.11-slim` pinned by digest (the project needs Python ≥3.11,<3.12);
  - the first stage exports `poetry.lock` to a requirements file with hashes, without dev dependencies; the final stage installs it with `pip install --require-hashes`;
  - the final stage has no Poetry, no compiler and no git;
  - it runs as a non-root user (uid 10001) with a read-only root filesystem, writable only where volumes are mounted plus a tmpfs `/tmp`;
  - the image is tagged with the git SHA it was built from (`helios:<sha>`), and the compose file builds it from the repo.
- What goes into the image: `helios/`, `bin/`, `prompts/`, `keys/*.pub.pem` and the files the runner needs to read, such as `schema.sql`. No data, captures, ledgers, `.env` or key files: those are mounted.
- (b) Publish the image to a registry (GHCR) and pin it by digest in the compose file. Better for a real "pull and run" install, but it needs a release pipeline. This is the Stage B Helm path.

### C-c. Pinning

- **Recommended:**
  - every `image:` in the compose file and every `FROM` line carries `@sha256:` (python, ollama);
  - the HELIOS image is reproducible from the lock file (hash-checked install) and labelled with its git SHA (`org.opencontainers.image.revision`);
  - a test (`tests/deploy/test_compose.py`) parses the compose file and the Dockerfile and fails on any tag without a digest, any `latest`, or any service other than `runner` that names `.env`;
  - the Ollama version is the newest one that serves the pinned model with the same digest. It is checked in the dry run (C-h).
- The model is pinned by its Ollama digest, not by the image (C-d).

### C-d. Model server and model identity

- **Recommended:**
  - the `model` service is Ollama in a container, on an internal network that is not published to the host;
  - `model-init` pulls `llama3.1:8b` into the named volume, then compares the served digest with `EXPECTED_MODEL_DIGEST`. On a mismatch it exits non-zero, so `runner` (which depends on it completing) never starts;
  - the L-pipe URL becomes configurable: `OLLAMA_BASE_URL` reads `HELIOS_OLLAMA_URL` from the environment, defaulting to today's `http://localhost:11434`. The runner sets it to `http://model:11434`.
- **Why the digest check matters:** an Ollama tag can be re-pushed. The digest, not the tag, is the model identity that entry 58 fixed. The run-start check already refuses a different digest; `model-init` makes the failure happen at install time.
- **Hardware caveat:** Docker on macOS has no GPU access, so the containerised model runs on CPU and is several times slower than the host's Metal Ollama. Greedy decoding on a different backend can also produce different tokens.
  - **Recommended:** confirmatory and exploratory evaluation runs keep using the host model server, the one the build data was calibrated on. The compose model server is the product deployment path.
  - The runner can point at the host server instead (`HELIOS_OLLAMA_URL=http://host.docker.internal:11434`) with no other change.
- (b) Mount the host's Ollama model directory into the container instead of pulling. This avoids a 4.9 GB download, but it ties the install to this machine, which is the opposite of a fresh install.

### C-e. Secrets

- **Recommended:**
  - `api` gets `env_file: .env.api` only. `runner` gets `env_file: .env` only. Neither file is copied into an image;
  - `api_keys.json` is mounted read-only into `api` at a fixed path;
  - the API's existing `DEVIATION_*` refusal stays as a second check, and the C-c test asserts that the compose file never gives `.env` to `api`;
  - `deploy/README.md` gives the first-time steps: generate the decisions secret and a key with the API CLI (run through `docker compose run`, so no host Python is needed), then `up`.
- (b) Compose `secrets:` (files mounted under `/run/secrets`). Slightly tidier, but the API and runner read environment variables today, so this needs a code change for no real gain on a single host.

### C-f. Network exposure

- **Recommended:**
  - the API listens on all interfaces inside its container, but the compose file publishes port 8080 **on the host's loopback interface only**. Exposing it wider is a deliberate edit, explained in the README;
  - `model` is on an internal network with no published port. `model-init` alone also joins a network with internet access, to pull the model;
  - `runner` joins only the internal network. The data it reads is mounted, so it needs no internet.
- `/health` stays unauthenticated, as in S4.1. Loopback-only publishing is what keeps that safe.

### C-g. Health checks and start order

- **Recommended:**
  - `api` health check: `GET /health` returns 200 (using Python's stdlib from inside the image, so no curl is needed);
  - `model` health check: the Ollama version endpoint answers;
  - `model-init` depends on `model` being healthy. `runner` depends on `model-init` having completed successfully;
  - `api` does not depend on the model at all, since v1 never calls it.

### C-h. Fresh-install test (done-when) and dry run

- **Recommended:** run it from a fresh `git clone` into a scratch directory, with no Poetry environment and the host Ollama stopped:
  1. `docker compose build`. The image builds from the lock file with hash checking;
  2. create the secret and a reviewer key through `docker compose run`;
  3. `docker compose up -d` with `HELIOS_CAMPAIGN` pointing at the OTel v3 build campaign (`camp_v3c`). Then check: `/health` is ok, CoE ledgers verify, one decision round trip works (view, then decision), and the decisions ledger verifies with `verify_ledgers.py`;
  4. `model-init` reports the expected digest;
  5. `docker compose --profile run run runner` on one build incident in a fresh campaign directory. The run completes, its CoE verifies, and its ranked list is compared with the host run of the same incident. Any difference is reported (C-d hardware caveat), with no analytic consequence because evaluation stays on the host;
  6. the C-c pinning test and the full gate pass.
- Build data only. No pool data is mounted.

## 4. Deviation entry

- **Recommended: none.**
  - The deployment changes no protocol, metric or test. `HELIOS_OLLAMA_URL` defaults to today's value, and model identity is still enforced by the run-start digest check.
  - Evaluation runs stay on the host model server (C-d).
- If you prefer a record of the "evaluation stays on the host model server" decision, it can go into the next entry that is needed anyway, or into the OSF addendum (S2-BL-05).

## 5. Files

| File | What |
|---|---|
| `deploy/compose.yaml` | Services, networks, volumes (C-a, C-f, C-g) |
| `deploy/Dockerfile` | HELIOS image (C-b) |
| `deploy/model_init.sh` | Pull and digest check (C-d) |
| `deploy/README.md` | Install steps, exposure, host model server option |
| `helios/pipelines/l_pipe/lpipe_config.py` | `HELIOS_OLLAMA_URL` override (C-d) |
| `tests/deploy/test_compose.py` | Pinning and secrets checks (C-c, C-e) |
| `.dockerignore` | Keeps data, ledgers, `.env*`, key files and caches out of the build context |

## 7. Implementation and fresh-install test (2026-11-14)

### What was built

- `deploy/compose.yaml`: `api`, `model-init`, `model`, `model-check`, `runner` (profile `run`), `admin` (profile `admin`); networks `front`, `egress`, `internal` (internal-only); volumes `ollama`, `runner-cache`. The HELIOS services run read-only, with all capabilities dropped and `no-new-privileges`.
- `deploy/Dockerfile`: `python:3.11-slim` pinned by digest. A first stage exports `poetry.lock` (Poetry 2.5.1, export plugin 1.10.1). The final stage installs it with `--require-hashes --no-deps`, as uid 10001, labelled with the git SHA.
- Ollama `0.40.16`, pinned by digest. It serves `llama3.1:8b` with digest `46e0c10c039e`, the one entry 58 fixed.
- `deploy/model_init.sh`: pulls the model with a private server, before `model` starts.
- `bin/check_model.py` (the `model-check` service): compares the served digest with `EXPECTED_MODEL_DIGEST`.
- `deploy/compose.host-model.yaml`: points the runner at the host model server (C-d).
- `deploy/README.md`: install steps, settings and exposure notes.
- `.dockerignore`: excludes data, ledgers, `.env*`, key files, tests and docs (except the price book).
- `tests/deploy/test_compose.py`: 13 tests covering pinning, secrets, exposure, start order, the build context, the model check, and the code changes below.

### Details settled while building

- **Pull before serve.** The Ollama server, not the client, downloads the model, so the server that pulls needs internet. `model-init` therefore runs its own short-lived server on the `egress` network. `model` starts only after it exits, so the two servers never share the volume, and `model` stays internal-only (C-f kept as approved).
- **Listening address.** The API listens on every interface inside its container, using an empty `--host`, and is published on the host's loopback address only. The owner authorised the loopback literal in the compose file, which the research-compliance hook blocks in tool writes.
- **Decisions ledger outside the campaign.** The campaign is mounted read-only, so the decisions ledger has its own mount. That needed `--decisions` on `helios_api.py serve` and on `verify_ledgers.py` (the latter fails, rather than skips, when the file or secret is missing).
- **Ledger commit.** The image has no git. The runner passes the build revision through `GITHUB_SHA`, which `hmac_chain._resolve_commit_sha` already reads.

### Defects the image exposed (fixed)

| Defect | Fix |
|---|---|
| `helios/evaluation/cost.py` imports `yaml`, but PyYAML was only installed through the dev tools | Declared as a main dependency; the lock still resolves to 6.0.3 |
| The runner creates the L-pipe cache under `data/cache/`, which is gitignored and mounted read-only, so a fresh install would fail | `HELIOS_LPIPE_CACHE` override (default unchanged). The runner keeps its own cache volume, so answers from the CPU model never enter the host's calibrated cache |
| `build_frozen` raised `FileNotFoundError` without git | Fails closed: the pool stays locked |

### Fresh-install test (C-h)

From a new clone of the branch (03c0a30), following `deploy/README.md`, with no Poetry environment used and a new, empty model volume:

| Check | Result |
|---|---|
| `build --no-cache` | Image `helios:03c0a30…` built from the lock file with hash checking |
| Secret and reviewer key via `admin` | Created; the key was printed once, and the key file stores only its digest |
| `up -d` until `model-check` exits 0 | 159 s, including the 4.9 GB model download |
| `model-check` | `llama3.1:8b digest 46e0c10c039e matches entry 58` |
| `/health` over `camp_v3c` | ok, 63 incidents, CoE 8/8 verified with the public key |
| Decision round trip | View 201, decision 201 (server time 4.1 ms), token reuse 409, decisions ledger verified on the host |
| Leakage scan | 11 responses, 0 matches |
| Runner on the build corpus (plan, then one confirmatory spec) | passed; its CoE verifies with the public key |
| Exposure | API published on loopback port 8080 only; `model` has no published port and is on the internal network only; no `DEVIATION_*` variable in the API container |

### Container model versus host (C-d caveat)

On two build specs (HELIOS-Full and noRouter, one incident), run against the container's CPU model with an empty cache, the final ranked list, scores, confidence and state equal the host runs in `camp_v3c`. The first publication of the noRouter run differs (the container's provisional top-1 was another service). That is a timing effect: the CPU model answers later, so the early verdict is published on fewer pipelines. It is why evaluation runs stay on the host model server. Two specs took 79 s on CPU.

### Gate

Full pre-push gate green: ruff, ruff format, black, mypy, pytest (coverage 96.55%), ledgers, verify-public (88 entries), captures, OSF freeze, tracking validation, notebook.

### Deviation entry

None, as approved (§4). No protocol, metric or test changed. The new environment overrides default to today's values, and model identity is still checked at run start.
