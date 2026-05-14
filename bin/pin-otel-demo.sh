#!/bin/bash
set -euo pipefail

# ================================================================
# HELIOS MVP — Pin OpenTelemetry Demo (v2.2.0)
# Purpose: Ensure exact, reproducible harness for all experiments (C1 compliance)
# ================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TARGET_DIR="$PROJECT_ROOT/external/otel-demo-pinned"

echo "=== HELIOS: Pinning OpenTelemetry Demo v2.2.0 ==="

# ------------------- Step 1: Check if already cloned -------------------
if [ -d "$TARGET_DIR/.git" ]; then
    echo "✅ OTEL Demo already cloned at: $TARGET_DIR"
    echo "   Skipping clone step (idempotent execution)."
    
    cd "$TARGET_DIR"
    
    # Verify we are still on the correct tag
    CURRENT_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "unknown")
    if [ "$CURRENT_TAG" != "2.2.0" ]; then
        echo "⚠️  Warning: Current checkout is not on tag 2.2.0 (found: $CURRENT_TAG)"
        echo "   Resetting to pinned tag..."
        git fetch --tags --depth=1 origin
        git checkout 2.2.0
    fi
else
    echo "📥 OTEL Demo not found. Cloning fresh copy..."
    
    # Clean any partial directory
    rm -rf "$TARGET_DIR"
    
    # Clone with shallow depth for speed and minimal size
    git clone --branch 2.2.0 --depth 1 \
        https://github.com/open-telemetry/opentelemetry-demo.git \
        "$TARGET_DIR"
    
    echo "✅ Successfully cloned OTEL Demo v2.2.0"
fi

# ------------------- Step 2: Apply Critical Fixes & Deviations -------------------
cd "$TARGET_DIR"

echo "🔧 Applying HELIOS environment fixes..."

# Fix 1: Pin DEMO_VERSION in .env to ensure stability (C1 compliance)
if [ -f ".env" ]; then
    sed -i 's/^DEMO_VERSION=latest/DEMO_VERSION=${IMAGE_VERSION}/' .env
    echo "   - Pinned DEMO_VERSION to \${IMAGE_VERSION} in .env"
fi

# ------------------- Step 3: Always run reference & documentation steps -------------------
COMMIT_SHA=$(git rev-parse HEAD)

# Save lightweight reference files
echo "$COMMIT_SHA" > "$PROJECT_ROOT/external/otel-demo-commit.txt"
echo "2.2.0" > TAG.txt

cat > REFERENCE.md << EOL
# OTEL Demo Pinning Reference

Tag: 2.2.0
Commit SHA: $COMMIT_SHA
Cloned/Verified on: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Repository: https://github.com/open-telemetry/opentelemetry-demo
EOL

# Auto-generate external/README.md (authoritative documentation)
cat > "$PROJECT_ROOT/external/README.md" << 'EOL'
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
EOL

echo "✅ Pinning complete. Reference files updated."
echo "✅ Documentation updated in external/README.md"
