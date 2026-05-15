# External Pinned Dependencies

## OpenTelemetry Demo (HELIOS Harness)

**Purpose**  
Sole execution harness for HELIOS MVP (Execution Plan §1 Decision #1). Used for all telemetry recording, fault injection, snapshots, and confirmatory runs (Stages 0–8).

**Pinning Details**
- Repository: https://github.com/open-telemetry/opentelemetry-demo
- Git Tag: `2.2.0`
- Commit SHA: See `otel-demo-commit.txt`
- Rationale: Guarantees identical telemetry schema, feature-flag behaviour, and Docker Compose environment — critical for C1 (runtime-enforced ablation discipline).

**Reproducibility**
```bash
./bin/pin-otel-demo.sh
```

---

## Applied Fixes & Deviations (Stage 0)

The following modifications were applied to the strictly pinned v2.2.0 version to ensure environment stability and resolve startup failures:

1.  **.env Version Pinning:**
    *   **Change:** Modified `external/otel-demo-pinned/.env` to set `DEMO_VERSION=${IMAGE_VERSION}`.
    *   **Reason:** Prevented the environment from pulling `latest` tags from GHCR, which were incompatible with the v2.2.0 source code. This freezes all images to the `2.2.0` release.

2.  **Frontend Proxy Local Build:**
    *   **Change:** Performed a local `docker compose build frontend-proxy`.
    *   **Reason:** The remote `latest` image for Envoy contained a configuration expecting a `telemetry-docs` cluster not present in the v2.2.0 template. Building locally from the pinned source resolved the `Proto constraint validation failed` error.

---

## Operational Guide

### 1. Start the environment
To start the full demo environment:
```bash
cd external/otel-demo-pinned
docker compose up -d
```
The application will be accessible at: **http://localhost:8080**

### 2. Stop the environment
To stop and remove containers:
```bash
cd external/otel-demo-pinned
docker compose down
```

### 3. Run in Minimal Mode (Ablation-friendly)
To run only the core infrastructure and the frontend (useful for lightweight research runs or testing specific components):
```bash
cd external/otel-demo-pinned
docker compose up -d \
  otel-collector \
  prometheus \
  jaeger \
  frontend-proxy \
  frontend
```

### 4. Modifying Source and Rebuilding Images
If you modify the source code in `external/otel-demo-pinned/src/`, you must rebuild the corresponding image to see the changes:

**Rebuild a specific service:**
```bash
cd external/otel-demo-pinned
docker compose build <service-name>
# Example: docker compose build frontend-proxy
```

**Rebuild and restart a service in one command:**
```bash
docker compose up -d --build <service-name>
```

**Rebuild all services:**
```bash
docker compose build
```

### 5. View Logs
To follow logs for a specific service (e.g., the proxy):
```bash
cd external/otel-demo-pinned
docker compose logs -f frontend-proxy
```

#### 5. Verify the web store and Telemetry
```
Web store: http://localhost:8080/
Grafana: http://localhost:8080/grafana/
Load Generator UI: http://localhost:8080/loadgen/
Jaeger UI: http://localhost:8080/jaeger/ui/
Tracetest UI: http://localhost:11633/, only when using make run-tracetesting
Flagd configurator UI: http://localhost:8080/feature
```

#### 6. OTEL Demo Verification
- Step 1: Verify OTEL Demo backends are live
```
  # Prometheus
  curl -s http://localhost:9090/-/ready
  # → "Prometheus Server is Ready."

  # Jaeger (via frontend proxy — stable port)
  curl -s http://localhost:8080/jaeger/ui/api/services | python3 -m json.tool | head -5
  # → JSON list of service names

  # OpenSearch
  curl -s http://localhost:32781/_cat/indices?v
  # → index listing with otel-logs-* entries

  # Identify actual host ports if they drift after Docker restart
  docker ps | grep -E 'jaeger|opensearch'

  Note: Docker assigns 32770+ ports dynamically. After a restart, Jaeger and OpenSearch ports may shift.
  Re-check with docker ps and update otel_demo_capture.py defaults if needed:
  # helios/telemetry/otel_demo_capture.py
  jaeger_url: str = "http://localhost:32770"   # was 32772 — update to match docker ps
  opensearch_url: str = "http://localhost:32781"  # was 32773 — update to match docker ps
```
- Record incidents 6–20
```
Protocol per incident: Enable fault flag → wait 6 min → capture → disable flag → wait 3 min baseline.
  Enable/disable faults at: http://localhost:8080/feature

  set -a; source .env; set +a

  # Run one capture per incident ID
  for ID in \
    s0-adhc-002 s0-adhc-003 \
    s0-cart-002 s0-cart-003 \
    s0-imgsl-002 s0-imgsl-003 s0-imgsl-004 \
    s0-pcat-002 s0-pcat-003 s0-pcat-004 s0-pcat-005 \
    s0-rcf-002 s0-rcf-003 s0-rcf-004 s0-rcf-005; do
    echo "=== capturing $ID ==="
    poetry run python bin/run_capture.py --incident-id "$ID"
  done

  Each capture writes 4 files to data/captures/{incident_id}/: manifest.json, p1_metrics.parquet,
  p2_traces.parquet, p3_logs.parquet.

```
- Verify all 20 captures (run 3× for determinism)
```
First, ensure bin/verify_captures.py lists all 20 incident IDs in _ALL_INCIDENT_IDS. Then:

  # Run 3 times — hashes and row counts must be identical across all runs
  poetry run python bin/verify_captures.py   # run 1
  poetry run python bin/verify_captures.py   # run 2
  poetry run python bin/verify_captures.py   # run 3
  # Expected: [OK] for all 20 incidents, "All snapshots verified OK"

```
- Run helios run across the full 20-incident corpus
```
 set -a; source .env; set +a
  poetry run python bin/helios_run.py \
    --variant HELIOS-Full \
    --corpus data/captures/
  # Expected output:
  # [helios run] variant=HELIOS-Full corpus=data/captures
  # [helios run] done
```
- Confirm outcome counts in ReconciliationLedger
```
python3 - <<'EOF'
  import json, pathlib
  rows = [json.loads(l) for l in pathlib.Path('reconciliation_ledger.jsonl').read_text().splitlines() if
  l.strip()]
  outcomes = [r['outcome'] for r in rows]
  print('total:', len(outcomes))
  for o in ['passed', 'excluded', 'skipped']:
      print(f'  {o}: {outcomes.count(o)}')
  EOF
  # Expected: passed: 20  excluded: 0  skipped: 0
  # (total may be higher if ledger accumulated from prior test runs — check the count of "passed")

```
- Verify HMAC chain integrity
```
set -a; source .env; set +a
  poetry run python - <<'EOF'
  import os
  from pathlib import Path
  from helios.orchestrator.ledger import ReconciliationLedger
  key = os.environ['DEVIATION_HMAC_SECRET'].encode()
  ledger = ReconciliationLedger(key=key, log_path=Path('reconciliation_ledger.jsonl'))
  ok, msg = ledger.verify()
  print(('OK' if ok else 'FAIL') + ': ' + msg)
  EOF
  # Expected: OK: Chain verified.
```
- Commit corpus and tag milestone
```
# Stage captures, ledger, and any changed scripts
  git add data/captures/ reconciliation_ledger.jsonl data/snapshot_registry.jsonl
  git add bin/verify_captures.py helios/telemetry/otel_demo_capture.py  # if ports were fixed

  git commit -m "data(m1): 20-incident calibration corpus + reconciliation ledger — full C1 gate compliance"

  # Apply milestone tag
  git tag milestone-1-exit
  git push origin milestone-1-exit

  # Also push schema freeze tag if not yet done
  git push origin schema-draft-v0.1

```