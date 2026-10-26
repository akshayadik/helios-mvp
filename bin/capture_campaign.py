#!/usr/bin/env python3
"""S1.2 OTel Demo build-capture campaign (helios/adapters/otel_campaign.py).

Usage (from repo root, with the pinned demo running; needs the ledger key):
    set -a; source .env; set +a
    poetry run python bin/capture_campaign.py preflight
    poetry run python bin/capture_campaign.py run [--limit N] [--reps 7]
    poetry run python bin/capture_campaign.py status
    poetry run python bin/capture_campaign.py verify
    poetry run python bin/capture_campaign.py finalize

``run`` resumes where it stopped: cases already in the signed ground truth are
skipped, an interrupted capture is recorded again. Each case takes about
13 minutes (1 min recovery, 5 min normal, 5 min fault, 1 min ingest lag,
capture). Output prints counts and progress only, never an incident ID.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from bin.run_capture import _write_snapshot_hash
from helios.adapters.otel_campaign import (
    CORPUS,
    DEFAULT_REPS,
    INGEST_LAG_S,
    POST_S,
    PRE_S,
    RECOVERY_S,
    SLICE_S,
    Campaign,
    FlagdFile,
    GroundTruthFile,
    PlannedCase,
    plan,
)
from helios.telemetry.otel_demo_capture import build_campaign_capture
from helios.telemetry.reader import CaptureReader
from helios.telemetry.seal import write_seal
from helios.vcl import set_current_manifest
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.variants import get_variant

if TYPE_CHECKING:
    from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = Path("external/otel-demo-pinned")
PINNED_COMMIT = Path("external/otel-demo-commit.txt")
FLAGD_PATH = DEMO_DIR / "src/flagd/demo.flagd.json"
CAPTURES_DIR = Path("data/otel/build")
GROUND_TRUTH = Path("data/otel/ground_truth_build.json")
CORPUS_MANIFEST = Path("data/otel/build_manifest.json")
PROMETHEUS_URL = "http://localhost:9090"
# Container ports from the demo's .env; host ports are looked up at run time
# because Docker assigns them anew on every start.
JAEGER_UI_PORT = 16686
OPENSEARCH_PORT = 9200
FLAGD_OFREP_PORT = 8016


def _compose(*args: str) -> str:
    out = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(DEMO_DIR / "docker-compose.yml"),
            "--project-directory",
            str(DEMO_DIR),
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def _host_url(service: str, port: int) -> str:
    mapped = _compose("port", service, str(port))  # "<host address>:<host port>"
    return f"http://localhost:{mapped.rsplit(':', 1)[1]}"


def _demo_commit() -> str:
    head = subprocess.run(
        ["git", "-C", str(DEMO_DIR), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    pinned = PINNED_COMMIT.read_text(encoding="utf-8").strip()
    if head != pinned:
        raise SystemExit(f"[campaign] demo is at {head[:12]}, pinned {pinned[:12]}")
    return head


def _flag_variant(ofrep_url: str, flag: str) -> str | None:
    req = urllib.request.Request(
        f"{ofrep_url}/ofrep/v1/evaluate/flags/{flag}",
        data=json.dumps({"context": {}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return str(json.loads(resp.read()).get("variant"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def _get(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return bool(resp.status < 300)
    except (urllib.error.URLError, TimeoutError):
        return False


def _ground_truth(key: bytes, commit: str) -> GroundTruthFile:
    return GroundTruthFile(REPO_ROOT / GROUND_TRUTH, key, demo_commit=commit)


def cmd_preflight() -> int:
    commit = _demo_commit()
    ok = True
    jaeger = _host_url("jaeger", JAEGER_UI_PORT)
    opensearch = _host_url("opensearch", OPENSEARCH_PORT)
    ofrep = _host_url("flagd", FLAGD_OFREP_PORT)
    checks = {
        "prometheus": _get(f"{PROMETHEUS_URL}/-/ready"),
        "jaeger": _get(f"{jaeger}/jaeger/ui/api/services"),
        "opensearch": _get(f"{opensearch}/_cluster/health"),
        "flagd (OFREP)": _flag_variant(ofrep, "adHighCpu") is not None,
    }
    for name, up in checks.items():
        print(f"[preflight] {name:14s}: {'up' if up else 'NOT REACHABLE'}")
        ok &= up
    flags = FlagdFile(REPO_ROOT / FLAGD_PATH).state()
    on = [k for k, v in flags.items() if v != "off"]
    free_gib = shutil.disk_usage(REPO_ROOT).free / 2**30
    print(f"[preflight] flags not off   : {len(on)}")
    print(f"[preflight] demo commit     : {commit[:12]} (pinned)")
    print(f"[preflight] free disk       : {free_gib:.0f} GiB")
    print(f"[preflight] {'READY' if ok else 'NOT READY'}")
    return 0 if ok else 1


def cmd_status(key: bytes, reps: int) -> int:
    cases = plan(reps)
    done = _ground_truth(key, _demo_commit()).cases()
    by_fault = Counter(c.fault.flag for c in cases if c.incident_id in done)
    print(f"[status] {len(done)}/{len(cases)} cases captured and labelled")
    for flag, n in sorted(by_fault.items()):
        print(f"[status]   {flag:28s} {n}")
    remaining = len(cases) - len(done)
    per_case_min = (RECOVERY_S + PRE_S + POST_S + INGEST_LAG_S) / 60 + 1
    print(f"[status] about {remaining * per_case_min / 60:.1f} h left")
    return 0


def cmd_run(key: bytes, reps: int, limit: int | None) -> int:
    commit = _demo_commit()
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    jaeger = _host_url("jaeger", JAEGER_UI_PORT)
    opensearch = _host_url("opensearch", OPENSEARCH_PORT)
    ofrep = _host_url("flagd", FLAGD_OFREP_PORT)

    def capture(case: PlannedCase, start: datetime, end: datetime) -> None:
        cap = build_campaign_capture(
            case.incident_id,
            manifest,
            output_dir=CAPTURES_DIR,
            prometheus_url=PROMETHEUS_URL,
            jaeger_url=jaeger,
            opensearch_url=opensearch,
            slice_s=SLICE_S,
        )
        window = cap.run(start, end)
        incident_dir = CAPTURES_DIR / case.incident_id
        _write_snapshot_hash(window, incident_dir / "manifest.json")
        write_seal(incident_dir, window, key)

    def restart(service: str) -> None:
        _compose("restart", service)
        print(f"[campaign] restarted {service}")

    campaign = Campaign(
        cases=plan(reps),
        captures_dir=CAPTURES_DIR,
        flagd=FlagdFile(REPO_ROOT / FLAGD_PATH),
        ground_truth=_ground_truth(key, commit),
        capture=capture,
        confirm_flag=lambda flag, variant: _flag_variant(ofrep, flag) == variant,
        restart=restart,
        sleep=time.sleep,
    )
    captured = campaign.run(limit)
    print(f"[campaign] captured {captured} case(s) this run")
    return cmd_status(key, reps)


def cmd_verify(key: bytes) -> int:
    done = _ground_truth(key, _demo_commit()).cases()
    reader = CaptureReader(CAPTURES_DIR, seal_key=key)
    bad = 0
    for incident_id in sorted(done):
        try:
            result = reader.read(incident_id)
        except FileNotFoundError:
            bad += 1
            continue
        bad += not result.intact
    print(f"[verify] ground truth signature OK; {len(done)} labelled cases")
    print(f"[verify] {len(done) - bad} intact (window hash + content seal), {bad} not")
    return 0 if bad == 0 and done else 1


def cmd_finalize(key: bytes) -> int:
    commit = _demo_commit()
    done = _ground_truth(key, commit).cases()
    body = {
        "kind": "otel-build-corpus",
        "corpus": CORPUS,
        "evaluation_phase": "exploratory",
        "demo_commit": commit,
        "protocol": {
            "pre_s": PRE_S,
            "post_s": POST_S,
            "recovery_s": RECOVERY_S,
            "ingest_lag_s": INGEST_LAG_S,
            "slice_s": SLICE_S,
        },
        # Sorted opaque IDs: the capture order would reveal the fault rotation.
        "case_order": sorted(done),
    }
    text = json.dumps(body, sort_keys=True, indent=2) + "\n"
    (REPO_ROOT / CORPUS_MANIFEST).write_text(text, encoding="utf-8")
    print(f"[finalize] {len(done)} cases written to {CORPUS_MANIFEST}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    for name in ("status", "run"):
        p = sub.add_parser(name)
        p.add_argument("--reps", type=int, default=DEFAULT_REPS)
        if name == "run":
            p.add_argument("--limit", type=int, default=None)
    sub.add_parser("verify")
    sub.add_parser("finalize")
    args = parser.parse_args(argv)
    if args.cmd == "preflight":
        return cmd_preflight()
    key = load_key()
    if args.cmd == "status":
        return cmd_status(key, args.reps)
    if args.cmd == "run":
        return cmd_run(key, args.reps, args.limit)
    if args.cmd == "verify":
        return cmd_verify(key)
    return cmd_finalize(key)


if __name__ == "__main__":
    sys.exit(main())
