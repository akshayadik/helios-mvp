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
