#!/usr/bin/env python3
"""Import RCAEval cases into the sealed HELIOS recorded format (S1.1, D11).

Usage (from repo root; convert and verify need the ledger key):
    set -a; source .env; set +a
    poetry run python bin/import_rcaeval.py fetch   --corpus build
    poetry run python bin/import_rcaeval.py convert --corpus build
    poetry run python bin/import_rcaeval.py verify  --corpus build
    (same with --corpus pool for the 240 confirmatory cases)

Layout (data/rcaeval/; the raw/, build/ and pool/ folders are git-ignored):
    raw/cases.parquet, raw/<case>/...       downloads, hash-checked
    raw/checksums_<corpus>.json             sha256 per downloaded file
    <corpus>/<opaque id>/                   sealed window (manifest, P1-P3, seal)
    ground_truth_<corpus>.json              signed; the only case-name <-> ID map
    <corpus>_manifest.json                  label-free; case order fixes run seeds

convert prints only counts and the manifest digest — no case names, labels or
results — so converting the pool reveals nothing about confirmatory outcomes.
The pool is sealed here but stays locked for runs until tag build-freeze.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_key
from helios.adapters.rcaeval import (
    CORPORA,
    INDEX_FILE,
    ConvertedCase,
    Fetcher,
    HttpFetcher,
    convert_case,
    fetch_case,
    load_index,
    select_corpus,
    verify_ground_truth,
    write_corpus_manifest,
    write_ground_truth,
)
from helios.schemas.telemetry import TelemetryWindow
from helios.telemetry.seal import check_seal
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance
from helios.vcl.variants import get_variant

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path("data/rcaeval")  # repo-relative on purpose (window paths)
INDEX_SHA256 = "c49a288920dbba2e8e724679a14636d5c7eb2b45426bba14007ef79a6c0ab1bb"


def _paths(corpus: str) -> dict[str, Path]:
    """Absolute paths under REPO_ROOT; nothing here depends on the cwd."""
    data = REPO_ROOT / DATA_ROOT
    return {
        "raw": data / "raw",
        "index": data / "raw" / INDEX_FILE,
        "checksums": data / "raw" / f"checksums_{corpus}.json",
        "out": data / corpus,
        "truth": data / f"ground_truth_{corpus}.json",
        "manifest": data / f"{corpus}_manifest.json",
    }


def _fetch_index(fetcher: Fetcher, dest: Path) -> None:
    if dest.is_file() and hashlib.sha256(dest.read_bytes()).hexdigest() == INDEX_SHA256:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    fetcher.download(INDEX_FILE, tmp)
    if hashlib.sha256(tmp.read_bytes()).hexdigest() != INDEX_SHA256:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"{INDEX_FILE}: hash does not match the pinned index")
    os.replace(tmp, dest)


def cmd_fetch(corpus: str, fetcher: Fetcher, limit: int | None) -> int:
    p = _paths(corpus)
    _fetch_index(fetcher, p["index"])
    records = select_corpus(load_index(p["index"]), corpus)[:limit]
    checksums: dict[str, dict[str, str]] = {}
    if p["checksums"].is_file():
        checksums = json.loads(p["checksums"].read_text(encoding="utf-8"))
    for n, rec in enumerate(records, 1):
        checksums[rec.case] = fetch_case(rec.case, p["raw"], fetcher)
        if n % 25 == 0 or n == len(records):
            print(f"[fetch] {corpus}: {n}/{len(records)} cases verified")
    p["checksums"].write_text(
        json.dumps(dict(sorted(checksums.items())), indent=2) + "\n", encoding="utf-8"
    )
    return 0


def cmd_convert(corpus: str, key: bytes, limit: int | None) -> int:
    p = _paths(corpus)
    if p["out"].exists() and any(p["out"].iterdir()):
        raise SystemExit(
            f"{p['out']} is not empty; conversion is all-or-nothing "
            "(delete the folder and rerun — it is regenerated deterministically)"
        )
    checksums = json.loads(p["checksums"].read_text(encoding="utf-8"))
    records = select_corpus(load_index(p["index"]), corpus)[:limit]
    missing = [r.case for r in records if r.case not in checksums]
    if missing:
        raise SystemExit(f"{len(missing)} cases not fetched; run fetch first")
    config_hash = get_variant("HELIOS-Full").compute_variant_config_hash()
    converted: list[ConvertedCase] = []
    for n, rec in enumerate(records, 1):
        converted.append(
            convert_case(
                rec,
                p["raw"] / rec.case,
                DATA_ROOT / corpus,
                corpus,
                seal_key=key,
                variant_config_hash=config_hash,
                root=REPO_ROOT,
            )
        )
        if n % 25 == 0 or n == len(records):
            print(f"[convert] {corpus}: {n}/{len(records)} cases sealed")
    if limit is not None:
        # A trial must never write the write-once ground truth or manifest.
        print(
            f"[convert] trial of {len(converted)} cases: no ground truth or manifest written"
        )
        return 0
    write_ground_truth(converted, p["truth"], corpus, key, checksums)
    _, digest = write_corpus_manifest(converted, p["manifest"], corpus)
    units = Counter(c.trace_time_unit or "none" for c in converted)
    notes = Counter(note for c in converted for note in c.notes)
    flagged = sum(1 for c in converted if any(c.injection_signatures.values()))
    print(f"[convert] trace time units: {dict(units)}")
    print(f"[convert] notes: {dict(notes) or 'none'}")
    print(f"[convert] cases with injection-tool strings in logs: {flagged}")
    print(f"[convert] {p['manifest']} digest {digest}")
    return 0


def cmd_verify(corpus: str, key: bytes) -> int:
    """Check every seal against the manifest, the manifest digest and the
    ground-truth signature — without reading any window through CaptureReader,
    so it works while the pool is locked."""
    p = _paths(corpus)
    manifest = json.loads(p["manifest"].read_text(encoding="utf-8"))
    digest = manifest.pop("manifest_digest")
    body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    errors: list[str] = []
    if hashlib.sha256(body).hexdigest() != digest:
        errors.append("manifest digest does not match its content")
    try:
        truth = verify_ground_truth(p["truth"], key)
    except ValueError as exc:
        errors.append(str(exc))
        truth = {}
    if truth and sorted(truth) != manifest["case_order"]:
        errors.append("ground truth and manifest list different cases")
    for incident_id in manifest["case_order"]:
        case_dir = p["out"] / incident_id
        raw = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
        stored = raw.pop("window_hash")
        window = TelemetryWindow(**raw)
        if window.compute_window_hash() != stored:
            errors.append(f"{incident_id}: window hash mismatch")
        problem = check_seal(case_dir, window, key, base=REPO_ROOT)
        if problem:
            errors.append(f"{incident_id}: {problem}")
        sealed = hashlib.sha256(
            (case_dir / "content_seal.json").read_bytes()
        ).hexdigest()
        if sealed != manifest["cases"][incident_id]["seal_sha256"]:
            errors.append(f"{incident_id}: seal differs from the corpus manifest")
    for err in errors:
        print(f"[verify] FAIL {err}")
    n = len(manifest["case_order"])
    bad = {i for i in manifest["case_order"] if any(e.startswith(i) for e in errors)}
    print(
        f"[verify] {corpus}: {n - len(bad)}/{n} cases OK, {len(errors)} problem(s)"
        f" (dataset revision {manifest['dataset_revision'][:12]}, digest {digest[:12]})"
    )
    return 1 if errors else 0


def main(argv: list[str] | None = None, fetcher: Fetcher | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("command", choices=["fetch", "convert", "verify"])
    parser.add_argument("--corpus", choices=sorted(CORPORA), required=True)
    parser.add_argument("--limit", type=int, default=None, help="first N cases only")
    args = parser.parse_args(argv)
    if args.command == "fetch":
        return cmd_fetch(args.corpus, fetcher or HttpFetcher(), args.limit)
    key = load_key()
    if args.command == "convert":
        return cmd_convert(args.corpus, key, args.limit)
    return cmd_verify(args.corpus, key)


if __name__ == "__main__":
    sys.exit(main())
