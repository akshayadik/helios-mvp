#!/usr/bin/env python3
"""OSF protocol freeze — generate and verify research artefacts.

Usage:
    python bin/verify_osf_freeze.py --generate
    python bin/verify_osf_freeze.py --verify
    python bin/verify_osf_freeze.py --populate-prereg
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import yaml

from helios.pipelines.l_pipe.lpipe_config import (
    EXPECTED_PROMPT_SHA,
    MODEL_NAME,
    PROMPT_VERSION,
)
from helios.pipelines.l_pipe.prompt_registry import PROMPT_PATH
from helios.research.analysis_plan import (
    FAMILY_A_HYPOTHESES,
    FAMILY_B_HYPOTHESES,
    _hypothesis_for_variant,
    _status_for_variant,
)
from helios.research.seeds import SEED_REGISTRY
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.registry import VCLFlag as _VCLFlagEnum
from helios.vcl.utils import canonical_json
from helios.vcl.variants import CONFIRMATORY_VARIANTS

OSF_DIR = Path("research/osf")
CAPTURES_DIR = Path("data/captures")
CALIBRATED_PARAMS_PATH = Path("data/calibrated_params.json")
PREREG_PATH = OSF_DIR / "preregistration.md"
_REGISTRY_PATH = Path("docs/tracking/prompt_version_registry.md")

_VCL_FLAG_KEYS = {f.value for f in _VCLFlagEnum}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _fault_class(incident_id: str) -> str:
    parts = incident_id.split("-")
    return parts[1] if len(parts) >= 3 else "unknown"


def _vcl_freeze_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD:helios/vcl/variants.py"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.warning("vcl_freeze_sha: git unavailable — using sentinel")
        return "git-unavailable"


def _verify_artefact(path: Path, regenerated: dict) -> bool:  # type: ignore[type-arg]
    on_disk_raw = path.read_bytes().replace(b"\r\n", b"\n")
    on_disk = json.loads(on_disk_raw)
    # Inject frozen timestamp so content comparison is clock-independent
    regenerated["generated_at_iso"] = on_disk["generated_at_iso"]
    regenerated_bytes = (canonical_json(regenerated) + "\n").encode("utf-8")
    return on_disk_raw == regenerated_bytes


def _generate_manifest_sig(osf_dir: Path) -> None:
    json_files = sorted(f for f in osf_dir.glob("*.json"))
    concatenated = b"".join(f.read_bytes().replace(b"\r\n", b"\n") for f in json_files)
    sig = hashlib.sha256(concatenated).hexdigest()
    (osf_dir / "manifest_sig.txt").write_bytes(sig.encode("utf-8"))


def _preflight_generate(captures_dir: Path, calibrated_params_path: Path) -> None:
    """Fail fast before writing any OSF artefact."""
    errors: list[str] = []

    if EXPECTED_PROMPT_SHA is None:
        errors.append(
            "EXPECTED_PROMPT_SHA is None — complete Spec 2 bootstrap before --generate"
        )
    if not PROMPT_PATH.exists():
        errors.append(f"rca_v1.txt not found at {PROMPT_PATH}")

    if not _REGISTRY_PATH.exists():
        errors.append(f"prompt_version_registry.md not found at {_REGISTRY_PATH}")
    else:
        try:
            front_matter = _REGISTRY_PATH.read_text(encoding="utf-8").split("---")[1]
            reg = yaml.safe_load(front_matter) or {}
            if not reg.get("entries", {}).get("rca_v1"):
                errors.append(
                    "prompt_version_registry.md missing 'rca_v1' entry — "
                    "complete Spec 2 bootstrap after committing rca_v1.txt"
                )
        except Exception as exc:
            errors.append(f"prompt_version_registry.md YAML parse failed: {exc}")

    missing_snapshot_hash: list[str] = []
    wrong_schema: list[str] = []
    if captures_dir.exists():
        for d in sorted(captures_dir.iterdir()):
            mp = d / "manifest.json"
            if not d.is_dir() or not mp.exists():
                continue
            cap = json.loads(mp.read_bytes())
            if cap.get("schema_version") != "schema-draft-v0.2":
                wrong_schema.append(d.name)
            if not cap.get("snapshot_hash"):
                missing_snapshot_hash.append(d.name)
    if wrong_schema:
        errors.append(f"Captures not on schema-draft-v0.2: {wrong_schema}")
    if missing_snapshot_hash:
        errors.append(f"Captures missing snapshot_hash: {missing_snapshot_hash}")

    if calibrated_params_path.exists():
        params = json.loads(calibrated_params_path.read_bytes())
        required = {
            "gpipe_hr_at_3_held_out",
            "dpipe_hr_at_3_held_out",
            "gate_passed",
            "n_incidents_triggered",
        }
        missing = required - params.keys()
        if missing:
            errors.append(
                f"calibrated_params.json missing G-pipe fields {missing} — "
                "run scripts/calibrate_gpipe.py first"
            )
    else:
        errors.append(f"calibrated_params.json not found at {calibrated_params_path}")

    result = subprocess.run(
        ["poetry", "run", "python", "bin/log_deviation.py", "verify"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        errors.append(f"Deviation log chain failed: {result.stdout.strip()}")

    if errors:
        print("--generate PREFLIGHT FAILED — fix all errors before re-running:\n")
        for e in errors:
            print(f"  * {e}")
        sys.exit(1)


def _build_seeds_dict() -> dict:  # type: ignore[type-arg]
    return {
        "schema_version": "v1",
        "generated_at_iso": _now_iso(),
        "seeds": SEED_REGISTRY,
    }


def _build_prompt_sha_dict() -> dict:  # type: ignore[type-arg]
    front_matter = _REGISTRY_PATH.read_text(encoding="utf-8").split("---")[1]
    reg = yaml.safe_load(front_matter)
    entry = reg["entries"]["rca_v1"]
    # NOTE: YAML key is "prompt_sha256" (not "sha256") — critical bug fix vs plan
    return {
        "schema_version": "v1",
        "generated_at_iso": _now_iso(),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": entry["prompt_sha256"],
        "model_name": MODEL_NAME,
        "model_family": "llama3.1",
        "frozen_at_milestone": "Milestone 3",
        "note": (
            "Production target: llama3.1:70b via vLLM. "
            "Deviation logged (see deviation_log entries 11-12)."
        ),
    }


def _build_thresholds_dict() -> dict:  # type: ignore[type-arg]
    from helios.pipelines.d_pipe import dpipe_config
    from helios.pipelines.g_pipe.gpipe_config import (
        DISAGREEMENT_THRESHOLD,
        GPIPE_PPR_ALPHA,
    )

    params = json.loads(CALIBRATED_PARAMS_PATH.read_bytes())
    return {
        "schema_version": "v1",
        "generated_at_iso": _now_iso(),
        "dpipe": {
            "calibration_incidents": params.get("n_calibration_incidents", 15),
            "frozen_at_milestone": "Milestone 2",
            "integrity_rate_gate": dpipe_config.INTEGRITY_RATE_GATE,
            "loo_cv_cpr": params.get("loo_cv_mean_cpr"),
            "loo_cv_hr_at_3": params.get("loo_cv_mean_hr_at_3"),
            "ppr_alpha": GPIPE_PPR_ALPHA,
            "pruner_efficacy_gate": dpipe_config.PRUNER_EFFICACY_GATE,
            "pruner_threshold": dpipe_config.PRUNER_THRESHOLD,
            "rho_threshold": params.get("rho_threshold"),
            "topology_boost_factor": params.get("topology_boost_factor"),
            "w_error": params.get("w_error"),
        },
        "gpipe": {
            "disagreement_threshold": DISAGREEMENT_THRESHOLD,
            "ppr_alpha": GPIPE_PPR_ALPHA,
            "frozen_at_milestone": "Milestone 3",
            "gpipe_hr_at_3_held_out": params["gpipe_hr_at_3_held_out"],
            "dpipe_hr_at_3_held_out": params["dpipe_hr_at_3_held_out"],
            "gate_passed": params["gate_passed"],
            "n_incidents_triggered": params["n_incidents_triggered"],
        },
    }


def _build_variant_hashes_dict() -> dict:  # type: ignore[type-arg]
    vcl_sha = _vcl_freeze_sha()
    variants_out = []
    for name, manifest in CONFIRMATORY_VARIANTS.items():
        flags = {k: v for k, v in manifest.model_dump().items() if k in _VCL_FLAG_KEYS}
        variants_out.append(
            {
                "name": name,
                "variant_config_hash": manifest.compute_variant_config_hash(),
                "hypothesis": _hypothesis_for_variant(name),
                "status": _status_for_variant(name),
                "flags": flags,
            }
        )
    return {
        "schema_version": "v1",
        "generated_at_iso": _now_iso(),
        "vcl_freeze_sha": vcl_sha,
        "variants": variants_out,
    }


def _build_analysis_plan_dict() -> dict:  # type: ignore[type-arg]
    data: dict = {  # type: ignore[type-arg]
        "schema_version": "v1",
        "generated_at_iso": _now_iso(),
        "statistical_test": "Wilcoxon signed-rank (one-sided)",
        "correction": "Holm-Bonferroni",
        "family_alpha": 0.05,
        "alpha_at_rank_1": 0.00625,
        "effect_size_commitment": "Cohen h >= 0.276",
        "target_hr_at_3": 0.73,
        "baseline_hr_at_3": 0.6,
        "family_a_hypotheses": FAMILY_A_HYPOTHESES,
        "family_b_hypotheses": FAMILY_B_HYPOTHESES,
    }
    assert len(data["family_b_hypotheses"]) == 8, "Family B must have 8 entries"
    a_h6 = next(h for h in data["family_a_hypotheses"] if h["id"] == "A-H6")
    assert a_h6.get("filter"), "A-H6 must have a non-empty filter field"
    return data


def _build_corpus_manifest_dict() -> dict:  # type: ignore[type-arg]
    incidents = []
    if CAPTURES_DIR.exists():
        for d in sorted(CAPTURES_DIR.iterdir()):
            if not d.is_dir():
                continue
            manifest_path = d / "manifest.json"
            if not manifest_path.exists():
                continue
            cap = json.loads(manifest_path.read_bytes())
            incidents.append(
                {
                    "incident_id": cap["incident_id"],
                    "snapshot_hash": cap["snapshot_hash"],
                    "fault_class": _fault_class(cap["incident_id"]),
                }
            )
    return {
        "schema_version": "v1",
        "generated_at_iso": _now_iso(),
        "exploratory": {
            "phase": "exploratory",
            "environment": "OTEL Demo (local)",
            "incident_count": len(incidents),
            "parquet_schema_version": "v2",
            "incidents": incidents,
        },
        "confirmatory": {
            "phase": "confirmatory",
            "status": "deferred",
            "environment": "AIOpsLab",
            "target_incident_count": 174,
            "note": (
                "Confirmatory corpus freeze deferred to post-Milestone 4. "
                "No confirmatory data collected as of this freeze."
            ),
        },
    }


def _write_artefact(path: Path, data: dict) -> None:  # type: ignore[type-arg]
    path.write_bytes((canonical_json(data) + "\n").encode("utf-8"))


def _cmd_generate() -> None:
    _preflight_generate(CAPTURES_DIR, CALIBRATED_PARAMS_PATH)
    OSF_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OSF_DIR.parent) as _tmp:
        tmp_dir = Path(_tmp)
        _write_artefact(tmp_dir / "seeds.json", _build_seeds_dict())
        _write_artefact(tmp_dir / "prompt_sha.json", _build_prompt_sha_dict())
        _write_artefact(tmp_dir / "thresholds.json", _build_thresholds_dict())
        _write_artefact(tmp_dir / "variant_hashes.json", _build_variant_hashes_dict())
        _write_artefact(tmp_dir / "analysis_plan.json", _build_analysis_plan_dict())
        _write_artefact(tmp_dir / "corpus_manifest.json", _build_corpus_manifest_dict())
        _generate_manifest_sig(tmp_dir)
        for fname in sorted(tmp_dir.glob("*")):
            shutil.move(str(fname), str(OSF_DIR / fname.name))
    print(f"--generate: 7 artefacts written to {OSF_DIR}")


def _cmd_verify() -> None:
    errors: list[str] = []

    artefacts: list[tuple[str, dict]] = [  # type: ignore[type-arg]
        ("seeds.json", _build_seeds_dict()),
        ("prompt_sha.json", _build_prompt_sha_dict()),
        ("thresholds.json", _build_thresholds_dict()),
        ("variant_hashes.json", _build_variant_hashes_dict()),
        ("analysis_plan.json", _build_analysis_plan_dict()),
        ("corpus_manifest.json", _build_corpus_manifest_dict()),
    ]
    for fname, regen in artefacts:
        path = OSF_DIR / fname
        if not path.exists():
            errors.append(f"Missing: {path}")
            continue
        if not _verify_artefact(path, regen):
            errors.append(f"Content mismatch: {fname}")

    ap_path = OSF_DIR / "analysis_plan.json"
    if ap_path.exists():
        ap = json.loads(ap_path.read_bytes())
        a_h6_entries = [
            h for h in ap.get("family_a_hypotheses", []) if h["id"] == "A-H6"
        ]
        if not a_h6_entries or not a_h6_entries[0].get("filter"):
            errors.append("A-H6 missing filter field in analysis_plan.json")
        if len(ap.get("family_b_hypotheses", [])) != 8:
            errors.append("analysis_plan.json: family_b_hypotheses must have 8 entries")

    json_files = sorted(f for f in OSF_DIR.glob("*.json"))
    concatenated = b"".join(f.read_bytes().replace(b"\r\n", b"\n") for f in json_files)
    expected_sig = hashlib.sha256(concatenated).hexdigest()
    sig_path = OSF_DIR / "manifest_sig.txt"
    if not sig_path.exists():
        errors.append("Missing: manifest_sig.txt")
    elif sig_path.read_text().strip() != expected_sig:
        errors.append("manifest_sig.txt mismatch")

    prompt_sha_path = OSF_DIR / "prompt_sha.json"
    if prompt_sha_path.exists():
        frozen_sha = json.loads(prompt_sha_path.read_bytes())["prompt_sha256"]
        if EXPECTED_PROMPT_SHA is None:
            warnings.warn(
                "--verify: EXPECTED_PROMPT_SHA is None — tamper-guard not active; "
                "complete Spec 2 bootstrap before OSF deposit (G3-7)",
                stacklevel=2,
            )
        elif frozen_sha != EXPECTED_PROMPT_SHA:
            errors.append(
                "EXPECTED_PROMPT_SHA mismatch with prompt_sha.json prompt_sha256"
            )

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        sys.exit(1)
    print("--verify: all artefacts match. OSF freeze intact.")


def _cmd_populate_prereg() -> None:
    sha_table: dict[str, str] = {}
    for f in sorted(OSF_DIR.glob("*.json")):
        sha_table[f.name] = hashlib.sha256(
            f.read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
    sha_table["manifest_sig.txt"] = hashlib.sha256(
        (OSF_DIR / "manifest_sig.txt").read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()

    content = PREREG_PATH.read_text(encoding="utf-8")
    for filename, sha in sha_table.items():
        content = re.sub(
            r"(<!-- SHA:" + re.escape(filename) + r" -->)(?:`[0-9a-f]{64}`)?",
            r"\g<1>`" + sha + "`",
            content,
        )
    PREREG_PATH.write_text(content, encoding="utf-8")
    print(f"preregistration.md: {len(sha_table)} SHA markers populated")


def main() -> None:
    parser = argparse.ArgumentParser(description="OSF protocol freeze CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true")
    group.add_argument("--verify", action="store_true")
    group.add_argument("--populate-prereg", action="store_true")
    args = parser.parse_args()

    if args.generate:
        _cmd_generate()
    elif args.verify:
        _cmd_verify()
    else:
        _cmd_populate_prereg()


if __name__ == "__main__":
    main()
