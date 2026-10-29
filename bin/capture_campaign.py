#!/usr/bin/env python3
"""S1.2 OTel Demo build-capture campaign (helios/adapters/otel_campaign.py).

Usage (from repo root, with the pinned demo running; needs the ledger key):
    set -a; source .env; set +a
    poetry run python bin/capture_campaign.py preflight
    poetry run python bin/capture_campaign.py run [--limit N] [--reps 7] [--corpus C] [--faults F,F]
    poetry run python bin/capture_campaign.py status [--corpus C] [--faults F,F]
    poetry run python bin/capture_campaign.py verify [--corpus C]
    poetry run python bin/capture_campaign.py finalize [--corpus C]

``--corpus`` is ``otel_build`` (S1.2, default) or ``otel_build_v2`` (S2.1
recapture: normal period varied per case, 8 to 15 minutes; each case then
takes about 20 minutes), ``otel_build_v3`` (S2-M7-ENG10: as v2, plus span
metrics, attributed logs and the load generator set to 25 users through its
API and checked before every case) or ``otel_pilot_v3`` (the v3 protocol under
its own IDs; with ``--reps 1 --faults ...`` for a short pilot).

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
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from bin.run_capture import _write_snapshot_hash
from helios.adapters.otel_campaign import (
    CORPUS,
    CORPUS_PILOT_V3,
    CORPUS_V2,
    CORPUS_V3,
    DEFAULT_REPS,
    INGEST_LAG_S,
    POST_S,
    PRE_S,
    PRE_S_MAX,
    PRE_S_MIN,
    PRE_S_STEP,
    RECOVERY_S,
    SLICE_S,
    Campaign,
    FlagdFile,
    GroundTruthFile,
    PlannedCase,
    load_users_for,
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
CAPTURES_DIR_V2 = Path("data/otel/build_v2")
GROUND_TRUTH_V2 = Path("data/otel/ground_truth_build_v2.json")
CORPUS_MANIFEST_V2 = Path("data/otel/build_v2_manifest.json")
_V3_FILES = {
    CORPUS_V3: "build_v3",
    CORPUS_PILOT_V3: "pilot_v3",
}
CORPORA = (CORPUS, CORPUS_V2, CORPUS_V3, CORPUS_PILOT_V3)
LOCUST_PORT = 8089
_SPAWN_RATE = 5  # users started per second
_SPAWN_SETTLE_S = 30


def _paths(corpus: str) -> tuple[Path, Path, Path]:
    """Captures directory, signed ground truth and corpus manifest of a corpus."""
    if corpus == CORPUS_V2:
        return CAPTURES_DIR_V2, GROUND_TRUTH_V2, CORPUS_MANIFEST_V2
    if corpus in _V3_FILES:
        stem = _V3_FILES[corpus]
        return (
            Path(f"data/otel/{stem}"),
            Path(f"data/otel/ground_truth_{stem}.json"),
            Path(f"data/otel/{stem}_manifest.json"),
        )
    return CAPTURES_DIR, GROUND_TRUTH, CORPUS_MANIFEST


def _locust_call(url: str, form: dict[str, str] | None = None) -> dict[str, object]:
    """GET (``form`` None) or form-POST to the load generator's web API."""
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    with urllib.request.urlopen(url, data=data, timeout=10) as resp:
        payload: dict[str, object] = json.loads(resp.read())
    return payload


def set_load(locust_url: str, users: int) -> None:
    """Start (or re-scale) the load generator to ``users`` users."""
    _locust_call(
        f"{locust_url}/swarm",
        {"user_count": str(users), "spawn_rate": str(_SPAWN_RATE)},
    )


def check_load(locust_url: str, users: int) -> None:
    """Raise unless the load generator runs exactly ``users`` users."""
    stats = _locust_call(f"{locust_url}/stats/requests")
    running = stats.get("user_count")
    if running != users:
        raise RuntimeError(f"load generator runs {running} users, expected {users}")


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


def _ground_truth(key: bytes, commit: str, corpus: str = CORPUS) -> GroundTruthFile:
    return GroundTruthFile(
        REPO_ROOT / _paths(corpus)[1], key, demo_commit=commit, corpus=corpus
    )


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


def cmd_status(
    key: bytes,
    reps: int,
    corpus: str = CORPUS,
    faults: tuple[str, ...] | None = None,
) -> int:
    cases = plan(reps, corpus=corpus, faults=faults)
    done = _ground_truth(key, _demo_commit(), corpus).cases()
    by_fault = Counter(c.fault.flag for c in cases if c.incident_id in done)
    print(f"[status] {len(done)}/{len(cases)} cases captured and labelled")
    for flag, n in sorted(by_fault.items()):
        print(f"[status]   {flag:28s} {n}")
    left = [c for c in cases if c.incident_id not in done]
    seconds = sum(RECOVERY_S + c.pre_s + POST_S + INGEST_LAG_S + 60 for c in left)
    print(f"[status] about {seconds / 3600:.1f} h left")
    return 0


def cmd_run(
    key: bytes,
    reps: int,
    limit: int | None,
    corpus: str = CORPUS,
    faults: tuple[str, ...] | None = None,
) -> int:
    commit = _demo_commit()
    captures_dir = _paths(corpus)[0]
    manifest = get_variant("HELIOS-Full")
    set_current_manifest(manifest)
    jaeger = _host_url("jaeger", JAEGER_UI_PORT)
    opensearch = _host_url("opensearch", OPENSEARCH_PORT)
    ofrep = _host_url("flagd", FLAGD_OFREP_PORT)
    users = load_users_for(corpus)
    locust = _host_url("load-generator", LOCUST_PORT) if users is not None else ""
    if users is not None:
        set_load(locust, users)
        time.sleep(_SPAWN_SETTLE_S)
        check_load(locust, users)
        print(f"[campaign] load generator at {users} users")

    def load_check() -> None:
        if users is not None:  # v1/v2 never enforced the load
            check_load(locust, users)

    def capture(case: PlannedCase, start: datetime, end: datetime) -> None:
        cap = build_campaign_capture(
            case.incident_id,
            manifest,
            output_dir=captures_dir,
            prometheus_url=PROMETHEUS_URL,
            jaeger_url=jaeger,
            opensearch_url=opensearch,
            slice_s=SLICE_S,
            span_metrics=corpus in _V3_FILES,
        )
        window = cap.run(start, end)
        incident_dir = captures_dir / case.incident_id
        _write_snapshot_hash(window, incident_dir / "manifest.json")
        write_seal(incident_dir, window, key)

    def restart(service: str) -> None:
        _compose("restart", service)
        print(f"[campaign] restarted {service}")

    campaign = Campaign(
        cases=plan(reps, corpus=corpus, faults=faults),
        captures_dir=captures_dir,
        flagd=FlagdFile(REPO_ROOT / FLAGD_PATH),
        ground_truth=_ground_truth(key, commit, corpus),
        capture=capture,
        confirm_flag=lambda flag, variant: _flag_variant(ofrep, flag) == variant,
        restart=restart,
        sleep=time.sleep,
        load_users=users,
        check_load=load_check,
    )
    captured = campaign.run(limit)
    print(f"[campaign] captured {captured} case(s) this run")
    return cmd_status(key, reps, corpus, faults)


def cmd_verify(key: bytes, corpus: str = CORPUS) -> int:
    done = _ground_truth(key, _demo_commit(), corpus).cases()
    reader = CaptureReader(_paths(corpus)[0], seal_key=key)
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


def cmd_finalize(key: bytes, corpus: str = CORPUS) -> int:
    commit = _demo_commit()
    done = _ground_truth(key, commit, corpus).cases()
    manifest = _paths(corpus)[2]
    body = {
        "kind": "otel-build-corpus",
        "corpus": corpus,
        "evaluation_phase": "exploratory",
        "demo_commit": commit,
        "protocol": {
            "pre_s": (
                {"min": PRE_S_MIN, "max": PRE_S_MAX, "step": PRE_S_STEP}
                if corpus != CORPUS
                else PRE_S
            ),
            **(
                {"load_users": load_users_for(corpus), "metrics": "span_metrics"}
                if corpus in _V3_FILES
                else {}
            ),
            "post_s": POST_S,
            "recovery_s": RECOVERY_S,
            "ingest_lag_s": INGEST_LAG_S,
            "slice_s": SLICE_S,
        },
        # Sorted opaque IDs: the capture order would reveal the fault rotation.
        "case_order": sorted(done),
    }
    text = json.dumps(body, sort_keys=True, indent=2) + "\n"
    (REPO_ROOT / manifest).write_text(text, encoding="utf-8")
    print(f"[finalize] {len(done)} cases written to {manifest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    for name in ("status", "run"):
        p = sub.add_parser(name)
        p.add_argument("--reps", type=int, default=DEFAULT_REPS)
        p.add_argument("--faults", type=lambda v: tuple(v.split(",")), default=None)
        if name == "run":
            p.add_argument("--limit", type=int, default=None)
    for name in ("verify", "finalize"):
        sub.add_parser(name)
    for p in sub.choices.values():
        if p.prog.split()[-1] != "preflight":
            p.add_argument("--corpus", choices=CORPORA, default=CORPUS)
    args = parser.parse_args(argv)
    if args.cmd == "preflight":
        return cmd_preflight()
    key = load_key()
    if args.cmd == "status":
        return cmd_status(key, args.reps, args.corpus, args.faults)
    if args.cmd == "run":
        return cmd_run(key, args.reps, args.limit, args.corpus, args.faults)
    if args.cmd == "verify":
        return cmd_verify(key, args.corpus)
    return cmd_finalize(key, args.corpus)


if __name__ == "__main__":
    sys.exit(main())
