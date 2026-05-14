# Step-by-step: 5 Parquet Recordings Across ≥3 Fault Classes

## Prerequisites (one-time check)
```bash
# All three backends must be reachable before starting
curl -s http://localhost:9090/-/ready          # → "Prometheus Server is Ready."
curl -s http://localhost:32772/jaeger/ui/api/services | python3 -m json.tool | head -5
curl -s http://localhost:32773/otel-logs-*/_count  # → {"count": N, ...}
```
## Recording protocol (repeat for each of the 5 incidents)
- The capture script grabs the last 5 minutes of telemetry. The protocol is:
```text
Enable fault → wait 6 min (1 min stabilize + 5 min fault window) → run capture → disable fault → wait 3 min baseline
```
6 minutes ensures the entire 5-minute capture window falls within the fault period.

### Incident 1 — s0-adhc-001 (adHighCpu · Resource)
1. Open http://localhost:8080/feature → toggle adHighCpu ON
2. Wait 6 minutes
3. Run the capture:
```python
poetry run python bin/run_capture.py --incident-id s0-adhc-001
```
4. Toggle adHighCpu OFF → wait 3 minutes for baseline recovery
Expected output:
```text
[capture] incident_id   : s0-adhc-001
[capture] variant       : HELIOS-Full
[capture] window_start  : 2026-05-14T09:02:08.815920+00:00
[capture] window_end    : 2026-05-14T09:07:08.815920+00:00
[capture] variant_hash  : 20ab0977d268d044...
[capture] querying backends ...
[capture] DONE
[capture] window_hash   : 7e5ffdd5ebc5510f...
[capture] p1_metrics    : data/captures/s0-adhc-001/p1_metrics.parquet
[capture] p2_traces     : data/captures/s0-adhc-001/p2_traces.parquet
[capture] p3_logs       : data/captures/s0-adhc-001/p3_logs.parquet
[capture] manifest.json : data/captures/s0-adhc-001/manifest.json
```
### Incident 2 — s0-cart-001 (cartFailure · Dependency)

1. Enable: http://localhost:8080/feature → cartFailure ON
2. Wait 6 minutes
3. Run the command
```python
poetry run python bin/run_capture.py --incident-id s0-cart-001
```
4. Disable → wait 3 minutes
```
Verification signal: rpc.grpc.status_code != OK visible in p2_traces for cart service.
```

### Incident 3 — s0-imgsl-001 (imageSlowLoad · Network)
1. Enable: http://localhost:8080/feature → imageSlowLoad ON
2. Wait 6 minutes
3. Run the command
```
poetry run python bin/run_capture.py --incident-id s0-imgsl-001
```
4. Disable → wait 3 minutes

### Incident 4 — s0-pcat-001 (productCatalogFailure · Code)
1. Enable: http://localhost:8080/feature → productCatalogFailure ON
2. Wait 6 minutes
3. Run the command
```python
poetry run python bin/run_capture.py --incident-id s0-pcat-001
```
4. Disable → wait 3 minutes

### Incident 5 — s0-rcf-001 (recommendationCacheFailure ·Dependency)
1. Enable: http://localhost:8080/feature → recommendationCacheFailure ON
2. Wait 6 minutes
3. Run the command
```python
poetry run python bin/run_capture.py --incident-id s0-rcf-001
```
4. Disable → wait 3 minutes

### Verify all 5 recordings (EG2 gate check)

```bash
# Check all 15 Parquet files + 5 manifests were written
ls -lh data/captures/*/

# Quick row-count check on each stream
poetry run python -c "
import pyarrow.parquet as pq, pathlib
for p in sorted(pathlib.Path('data/captures').rglob('*.parquet')):
    t = pq.read_table(p)
    print(f'{p.parent.name}/{p.name}: {t.num_rows} rows')
"

```
Expected: all 15 Parquets non-empty. If p2_traces is empty for a given incident, Jaeger's in-memory store may have expired — re-run that incident.

### What satisfies EG2

| Gate criterion             | How it's met                                                                                   |
| -------------------------- | ---------------------------------------------------------------------------------------------- |
| 5 Parquet recordings       | One per `incident_id` under `data/captures/`                                                   |
| ≥3 fault classes           | Resource (`adhc`) + Network (`imgsl`) + Dependency (`cart`, `rcf`) + Code (`pcat`) = 4 classes |
| Schema-validated           | `TelemetryWindow` `manifest.json` written per recording with `window_hash`                     |
| Fault active during window | 6-min wait guarantees the 5-min capture window is entirely within the fault period             |


One caveat: Jaeger uses in-memory storage. Do all 5 recordings in a single session without restarting docker compose, otherwise trace data from earlier incidents will be lost.

---

## Snapshot Verification (Spine Hardening)

After recording, use `CaptureReader` to verify every capture is intact and schema-valid. This is the reproducibility check: the same hash that was written at recording time must recompute identically from the Parquet + manifest data on disk.

### Verify a single incident

```python
from pathlib import Path
from helios.telemetry.reader import CaptureReader

reader = CaptureReader(Path("data/captures"))
result = reader.read("s0-cart-001")

print(f"incident_id   : {result.incident_id}")
print(f"hash_matches  : {result.hash_matches}")
print(f"stored_hash   : {result.stored_hash[:16]}...")
print(f"computed_hash : {result.computed_hash[:16]}...")
print(f"row_counts    : {result.stream_row_counts}")
```

Expected output (hash prefix will differ per recording):
```text
incident_id   : s0-cart-001
hash_matches  : True
stored_hash   : 3a9f1c7b2e840d5a...
computed_hash : 3a9f1c7b2e840d5a...
row_counts    : {'p1_metrics': 1520, 'p2_traces': 843, 'p3_logs': 2100}
```

### Verify all 5 recordings in one pass

```python
from pathlib import Path
from helios.telemetry.reader import CaptureReader

INCIDENT_IDS = [
    "s0-adhc-001",
    "s0-cart-001",
    "s0-imgsl-001",
    "s0-pcat-001",
    "s0-rcf-001",
]

reader = CaptureReader(Path("data/captures"))
all_ok = True

for iid in INCIDENT_IDS:
    result = reader.read(iid)
    status = "OK" if result.hash_matches else "TAMPERED"
    rows = result.stream_row_counts
    print(
        f"[{status}] {iid:20s}"
        f"  p1={rows.get('p1_metrics', 0):5d}"
        f"  p2={rows.get('p2_traces', 0):5d}"
        f"  p3={rows.get('p3_logs', 0):5d}"
    )
    if not result.hash_matches:
        all_ok = False

print()
print("All snapshots verified OK" if all_ok else "VERIFICATION FAILED — see TAMPERED rows above")
```

Expected output:
```text
[OK] s0-adhc-001          p1= 1520  p2=  620  p3= 1840
[OK] s0-cart-001          p1= 1520  p2=  843  p3= 2100
[OK] s0-imgsl-001         p1= 1520  p2=  510  p3= 1960
[OK] s0-pcat-001          p1= 1520  p2=  390  p3= 1750
[OK] s0-rcf-001           p1= 1520  p2=  470  p3= 1880

All snapshots verified OK
```

Row counts will differ by recording time. A `hash_matches: False` result means `manifest.json` was edited after recording — the Parquet files are the authoritative source, not the manifest.

### What verification checks

| Check | How |
|---|---|
| Snapshot hash integrity | `stored_hash` (from `manifest.json`) == `compute_window_hash()` recomputed from `TelemetryWindow` fields |
| Schema validity | `TelemetryWindow(**manifest_data)` construction raises `ValidationError` if any field is missing or wrong type |
| Parquet readability | Each `.parquet` file is opened with `pyarrow.parquet.read_table()` — a corrupt file raises here |
| Stream completeness | `stream_row_counts` reports 0 for any stream whose Parquet is missing or empty |

### Interpreting failures

| Symptom | Likely cause | Fix |
|---|---|---|
| `FileNotFoundError` | `manifest.json` missing — capture did not complete | Re-run `bin/run_capture.py` for that incident |
| `ValidationError` | `manifest.json` schema mismatch — written by a different schema version | Re-record; do not edit the manifest by hand |
| `hash_matches: False` | `manifest.json` was modified after recording | Restore from git or re-record |
| `p2_traces` row count = 0 | Jaeger in-memory store expired (docker restart) | Re-record that incident in a fresh session |

---

## Running verification from the command line

`bin/verify_captures.py` is the CLI equivalent of the inline Python above. It exits `0` on success and `1` on any failure.

### Verify all 5 incidents (default)

```bash
poetry run python bin/verify_captures.py
```

### Verify a single incident

```bash
poetry run python bin/verify_captures.py --incident-id s0-cart-001
```

### Verify against a non-default captures directory

```bash
poetry run python bin/verify_captures.py --captures-dir /mnt/archive/captures
```

### Expected output

```text
[verify] captures_dir : data/captures
[verify] incidents     : s0-adhc-001, s0-cart-001, s0-imgsl-001, s0-pcat-001, s0-rcf-001

[OK      ] s0-adhc-001           p1= 1520  p2=  620  p3= 1840  hash=3a9f1c7b2e84...
[OK      ] s0-cart-001           p1= 1520  p2=  843  p3= 2100  hash=7e5ffdd5ebc5...
[OK      ] s0-imgsl-001          p1= 1520  p2=  510  p3= 1960  hash=c4d2a8f19b30...
[OK      ] s0-pcat-001           p1= 1520  p2=  390  p3= 1750  hash=91e7b3620fc1...
[OK      ] s0-rcf-001            p1= 1520  p2=  470  p3= 1880  hash=58d4e0a72c9f...

[verify] All snapshots verified OK
```

Exit code `1` is returned and `TAMPERED` / `MISSING` labels appear if any snapshot fails verification.








