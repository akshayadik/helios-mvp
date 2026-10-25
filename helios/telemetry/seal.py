"""Content seal for recorded telemetry captures — C1 data integrity (§3.6.8, §5.1).

`window_hash` covers the TelemetryWindow fields only: incident metadata and the
Parquet *paths*. It does not change when a Parquet file's bytes change, and the
manifest's `snapshot_hash` annotation sits outside it. The content seal closes
that gap without touching the frozen TelemetryWindow schema or any hash:

    {incident_dir}/content_seal.json
        incident_id, manifest_sha256 (exact bytes of manifest.json),
        pillars: {stream: sha256 of the Parquet bytes the pipelines read},
        seal_signature: HMAC-SHA256 over the above (ledger key)

The HMAC matters: a plain hash next to the data can be recomputed by whoever
edits the data. A seal is written once, after the manifest is final, and is
never overwritten.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

if TYPE_CHECKING:
    from helios.schemas.telemetry import TelemetryWindow

__all__ = ["SEAL_FILENAME", "check_seal", "seal_fields", "write_seal"]

SEAL_FILENAME = "content_seal.json"
_SEAL_VERSION = 1
_SEAL_KIND = "capture-content"
_SIGNATURE_KEY = "seal_signature"
_STREAM_ATTRS: tuple[tuple[str, str], ...] = (
    ("p1_metrics", "p1_metrics_path"),
    ("p2_traces", "p2_traces_path"),
    ("p3_logs", "p3_logs_path"),
    ("p4_events", "p4_events_path"),
    ("p5_profiles", "p5_profiles_path"),
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _sign(key: bytes, fields: dict[str, Any]) -> str:
    if len(key) < 32:
        raise ValueError(f"Seal key must be at least 32 bytes (got {len(key)}).")
    payload = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def seal_fields(
    incident_dir: Path, window: TelemetryWindow, base: Path | None = None
) -> dict[str, Any]:
    """Hash the manifest and every declared Parquet stream as they are on disk.

    Streams are hashed at the path the window declares — the file the pipelines
    will read. A relative path resolves against ``base`` when given, else the
    working directory (repo-relative paths keep window_hash machine-independent).
    A declared stream whose file is missing raises FileNotFoundError.
    """
    pillars: dict[str, str] = {}
    for stream, attr in _STREAM_ATTRS:
        path_val = getattr(window, attr)
        if path_val is None:
            continue
        path = Path(str(path_val))
        if base is not None and not path.is_absolute():
            path = base / path
        if not path.is_file():
            raise FileNotFoundError(f"{stream} declared at {path} but not on disk")
        pillars[stream] = _sha256_file(path)
    return {
        "seal_version": _SEAL_VERSION,
        "seal_kind": _SEAL_KIND,
        "incident_id": window.incident_id,
        "manifest_sha256": _sha256_file(incident_dir / "manifest.json"),
        "pillars": pillars,
    }


def write_seal(
    incident_dir: Path, window: TelemetryWindow, key: bytes, base: Path | None = None
) -> Path:
    """Write the signed seal for a final capture. Refuses to overwrite."""
    seal_path = incident_dir / SEAL_FILENAME
    if seal_path.exists():
        raise FileExistsError(f"{seal_path} already exists; seals are write-once.")
    fields = seal_fields(incident_dir, window, base)
    seal = {**fields, _SIGNATURE_KEY: _sign(key, fields)}
    tmp = seal_path.with_name(seal_path.name + ".tmp")
    tmp.write_text(json.dumps(seal, sort_keys=True, indent=2) + "\n", "utf-8")
    os.replace(tmp, seal_path)
    return seal_path


def check_seal(
    incident_dir: Path, window: TelemetryWindow, key: bytes, base: Path | None = None
) -> str | None:
    """Return why the capture fails its seal, or None if sealed and unchanged."""
    seal_path = incident_dir / SEAL_FILENAME
    if not seal_path.exists():
        return f"no {SEAL_FILENAME}: capture content is unverified"
    try:
        stored = json.loads(seal_path.read_text(encoding="utf-8"))
        claimed = str(stored.pop(_SIGNATURE_KEY))
    except (json.JSONDecodeError, KeyError, AttributeError):
        return f"{SEAL_FILENAME} is unreadable or unsigned"
    if not hmac.compare_digest(_sign(key, stored), claimed):
        return f"{SEAL_FILENAME} signature does not verify"
    if (stored.get("seal_kind"), stored.get("seal_version")) != (
        _SEAL_KIND,
        _SEAL_VERSION,
    ):
        return f"unsupported seal {stored.get('seal_kind')!r} v{stored.get('seal_version')!r}"
    try:
        current = seal_fields(incident_dir, window, base)
    except FileNotFoundError as exc:
        return str(exc)
    if stored.get("incident_id") != current["incident_id"]:
        return (
            f"seal belongs to {stored.get('incident_id')!r}, "
            f"not {current['incident_id']!r}"
        )
    # A whole capture directory copied under another id is internally
    # consistent; its manifest paths would point at the other incident's data.
    if incident_dir.name != current["incident_id"]:
        return (
            f"capture directory {incident_dir.name!r} holds incident "
            f"{current['incident_id']!r}"
        )
    if stored.get("manifest_sha256") != current["manifest_sha256"]:
        return "manifest.json bytes changed since sealing"
    sealed = stored.get("pillars", {})
    if set(sealed) != set(current["pillars"]):
        return (
            f"sealed streams {sorted(sealed)} != declared streams "
            f"{sorted(current['pillars'])}"
        )
    changed = sorted(s for s in sealed if sealed[s] != current["pillars"][s])
    if changed:
        return f"content changed since sealing: {', '.join(changed)}"
    return None
