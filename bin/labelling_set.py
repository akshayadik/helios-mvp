"""Build a labelling set from signed CoE ledgers (S2.9 design §5.3).

Usage (from the repository root):
    set -a; source .env; set +a
    poetry run python bin/labelling_set.py --coe DIR [DIR ...] --out DIR \\
        --share training|confirmatory --rubric docs/research/h_fact_rubric.md

Verifies every ``*.coe.jsonl`` (HMAC chain and Ed25519 anchor) before reading
it, refuses confirmatory entries before tag ``build-freeze`` (D11), never opens
a ground-truth file (entry 65), and writes set.json (what raters may see),
key.json (what they may not) and manifest.json once. Prints counts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import PUBLIC_KEY_FILE, load_key, load_public_key_file
from helios.labelling.sets import (
    CONFIRMATORY_PLANTED_SHARE,
    TRAINING_PLANTED_SHARE,
    build_set,
    derived_seed,
    rubric_sha,
    write_set,
)
from helios.labelling.training import onboarding_set, select_training
from helios.narrative.params import load_narrator_params
from helios.orchestrator.coe import CoELedger
from helios.telemetry.pool_lock import build_frozen
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

__all__ = ["build_frozen", "main", "rubric_sha"]

SHARES = {
    "training": TRAINING_PLANTED_SHARE,
    "confirmatory": CONFIRMATORY_PLANTED_SHARE,
}


def _load(
    directories: list[Path], key: bytes, public_path: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | str:
    """Entries and the ledger records, or why they cannot be used."""
    public = load_public_key_file(public_path)
    if public is None:
        return f"no public key at {public_path}"
    entries: list[dict[str, Any]] = []
    ledgers: list[dict[str, Any]] = []
    for directory in directories:
        for path in sorted(directory.glob("*.coe.jsonl")):
            log = CoELedger(key, path, ed25519_public=public)
            ok, msg = log.verify()
            if not ok:
                return f"{path.name}: {msg}"
            lines = [
                json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()
            ]
            entries += lines
            ledgers.append(
                {
                    "file": path.name,
                    "entries": len(lines),
                    "anchor_sha256": hashlib.sha256(
                        log.anchor_path.read_bytes()
                    ).hexdigest(),
                }
            )
    if not entries:
        return "no CoE entries found"
    return entries, ledgers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coe", type=Path, nargs="+", required=True, metavar="DIR")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--share", choices=sorted(SHARES), required=True)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, default=PUBLIC_KEY_FILE)
    parser.add_argument(
        "--per-arm", type=int, help="a training round: this many narratives per arm"
    )
    parser.add_argument(
        "--exclude-sets",
        type=Path,
        nargs="*",
        default=[],
        metavar="SET_DIR",
        help="earlier rounds whose cases are not reused",
    )
    parser.add_argument("--onboarding", action="store_true", help="the onboarding set")
    args = parser.parse_args(argv)
    loaded = _load(args.coe, load_key(), args.public_key)
    if isinstance(loaded, str):
        print(f"[labelling] refused: {loaded}", file=sys.stderr)
        return 2
    entries, ledgers = loaded
    if (
        any(e.get("evaluation_phase") == "confirmatory" for e in entries)
        and not build_frozen()
    ):
        print(
            "[labelling] refused: confirmatory entries before build-freeze",
            file=sys.stderr,
        )
        return 2
    params, rubric = load_narrator_params(), rubric_sha(args.rubric)
    run_ids = sorted(str(e.get("run_id")) for e in entries)
    # Cases of earlier sets (rounds, onboarding) are never reused (review M10).
    used: set[str] = set()
    for earlier in args.exclude_sets:
        key = json.loads((earlier / "key.json").read_text("utf-8"))
        used |= {str(v["incident_id"]) for v in key.values()}
    fresh = [e for e in entries if str(e.get("incident_id")) not in used]
    if args.onboarding:
        s = onboarding_set(fresh, seed=derived_seed(run_ids, rubric), params=params)
    else:
        plant_from = None
        if args.per_arm is not None:
            chosen = select_training(
                fresh,
                n_per_arm=args.per_arm,
                seed=derived_seed(run_ids, rubric),
                exclude_cases=set(),
            )
            cases = {str(e["incident_id"]) for e in chosen}
            # Planted claims come from build cases outside the round (review M3).
            plant_from = [e for e in fresh if str(e["incident_id"]) not in cases]
            entries = [dict(e) for e in chosen]
        s = build_set(
            entries,
            planted_share=SHARES[args.share],
            rubric_sha=rubric,
            params=params,
            plant_from=plant_from,
        )
    s.manifest["ledgers"] = ledgers
    write_set(s, args.out)
    print(f"[labelling] {json.dumps(s.manifest['counts'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
