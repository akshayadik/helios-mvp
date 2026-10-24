"""RCAEval adapter (S1.1; D11 §1-§3; S0.1 findings F1-F5).

Turns RCAEval cases (Hugging Face Parquet copy, pinned revision) into sealed
HELIOS recorded windows:

    fetch     per-case download, every file checked against the hash the
              dataset publishes (SHA-256 for LFS files, git blob SHA-1 else)
    convert   metrics / traces / logs -> P1 / P2 / P3 Parquet in the HELIOS
              stream schemas, service names normalised (F4), candidate set =
              every service seen in any modality (F2, F5)
    seal      content seal (helios.telemetry.seal) after a leakage scan
    record    signed ground-truth file and a corpus manifest whose case order
              (sorted opaque IDs) fixes the run seeds (helios.research.seeds)

Leakage controls (F1): a case is stored under an **opaque incident ID**
derived from the registered opaque-ID seed; the RCAEval case name, the
root-cause service, the fault and the injection time are written only to the
ground-truth file, never into a window. Confirmatory windows stay locked
until tag build-freeze (helios.telemetry.pool_lock).

What the leakage scan can and cannot forbid: fault words such as ``cpu`` or
``socket`` are also metric names, and every service, the root cause included,
legitimately appears in the telemetry. The scan therefore forbids
label-carrying strings — the case name, any RCAEval case-name pattern and the
injection timestamp — and only *counts* fault-injection tool signatures in log
bodies, which are reported as a covariate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from helios.adapters.names import candidate_set, canonical
from helios.research.seeds import opaque_id_seed
from helios.schemas.telemetry import EvaluationPhase, TelemetryWindow
from helios.telemetry.seal import write_seal
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = [
    "BUILD_DATASETS",
    "CORPORA",
    "HF_REPO",
    "HF_REVISION",
    "POOL_DATASETS",
    "CaseRecord",
    "ConvertedCase",
    "Fetcher",
    "HttpFetcher",
    "LeakageError",
    "RemoteFile",
    "convert_case",
    "fetch_case",
    "leakage_findings",
    "load_index",
    "opaque_id",
    "select_corpus",
    "verify_ground_truth",
    "write_corpus_manifest",
    "write_ground_truth",
]

HELIOS_ENABLE_RCAEVAL_ADAPTER: bool = True

HF_REPO = "phamquiluan/RCAEval"
HF_REVISION = "afeacb11bcc94dadfd1c8f483ee4377b2b8b614e"  # 2026-08-02
INDEX_FILE = "cases.parquet"

POOL_DATASETS: tuple[str, ...] = ("re2ob", "re2tt", "re3ob", "re3tt")
BUILD_DATASETS: tuple[str, ...] = ("re1ob", "re1ss", "re1tt", "re2ss", "re3ss")
# corpus -> (datasets, opaque-ID seed slot, evaluation phase)
CORPORA: dict[str, tuple[tuple[str, ...], str, EvaluationPhase]] = {
    "pool": (POOL_DATASETS, "rcaeval_confirmatory", EvaluationPhase.CONFIRMATORY),
    "build": (BUILD_DATASETS, "rcaeval_build", EvaluationPhase.EXPLORATORY),
}

MANIFEST_SCHEMA_VERSION = "schema-draft-v0.2"  # same as bin/run_capture.py
_CASE_NAME = re.compile(r"re[123](ob|ss|tt)_", re.IGNORECASE)
_INJECTION_SIGNATURES: tuple[str, ...] = (
    "stress-ng",
    "chaos",
    "netem",
    "tc qdisc",
    "inject",
)
# Epoch magnitudes: seconds ~1.7e9, ms ~1.7e12, us ~1.7e15, ns ~1.7e18.
_TO_MICROSECONDS: tuple[tuple[float, int, str], ...] = (
    (1e17, -1000, "ns"),
    (1e14, 1, "us"),
    (1e11, 1000, "ms"),
    (1e8, 1_000_000, "s"),
)


# ── index ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CaseRecord:
    """One RCAEval case as listed in cases.parquet (the ground truth)."""

    case: str
    dataset: str  # e.g. re2ob
    system: str  # ob | tt | ss
    root_cause_service: str
    fault: str
    repetition: int
    inject_time: int
    has_logs: bool
    has_traces: bool


def load_index(path: Path) -> list[CaseRecord]:
    df = pd.read_parquet(path)
    records = [
        CaseRecord(
            case=str(r["case"]),
            dataset=str(r["case"]).split("_", 1)[0].lower(),
            system=str(r["system"]).lower(),
            root_cause_service=str(r["root_cause_service"]),
            fault=str(r["fault"]),
            repetition=int(r["repetition"]),
            inject_time=int(r["inject_time"]),
            has_logs=bool(r["has_logs"]),
            has_traces=bool(r["has_traces"]),
        )
        for r in df.to_dict("records")
    ]
    return sorted(records, key=lambda rec: rec.case)


def select_corpus(records: Iterable[CaseRecord], corpus: str) -> list[CaseRecord]:
    datasets = CORPORA[corpus][0]
    return [r for r in records if r.dataset in datasets]


def opaque_id(case: str, corpus: str) -> str:
    """128-bit opaque incident ID, keyed by the registered opaque-ID seed.

    Deterministic (same case and seed give the same ID on any machine) and
    carries nothing a pipeline could read back: 32 hex digits.
    """
    seed = opaque_id_seed(CORPORA[corpus][1])
    return hashlib.sha256(f"{seed}:{case}".encode()).hexdigest()[:32]


# ── fetch ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RemoteFile:
    path: str  # repository path, e.g. re2ss_carts_cpu_1/logs.parquet
    size: int
    sha256: str | None  # LFS files
    git_oid: str  # git blob SHA-1 (for non-LFS files)


class Fetcher(Protocol):
    def list_files(self, case: str) -> list[RemoteFile]: ...

    def download(self, path: str, dest: Path) -> None: ...


class HttpFetcher:
    """Hugging Face over HTTPS at the pinned revision (no extra dependency)."""

    def __init__(self, repo: str = HF_REPO, revision: str = HF_REVISION) -> None:
        self._repo = repo
        self._revision = revision

    def _get(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=120) as resp:
            data: bytes = resp.read()
        return data

    def list_files(self, case: str) -> list[RemoteFile]:
        url = (
            f"https://huggingface.co/api/datasets/{self._repo}/tree/"
            f"{self._revision}/{urllib.parse.quote(case)}"
        )
        entries = json.loads(self._get(url))
        return [
            RemoteFile(
                path=e["path"],
                size=int(e["size"]),
                sha256=(e.get("lfs") or {}).get("oid"),
                git_oid=e["oid"],
            )
            for e in entries
            if e.get("type") == "file"
        ]

    def download(self, path: str, dest: Path) -> None:
        url = (
            f"https://huggingface.co/datasets/{self._repo}/resolve/"
            f"{self._revision}/{urllib.parse.quote(path)}"
        )
        dest.write_bytes(self._get(url))


def _file_matches(path: Path, remote: RemoteFile) -> bool:
    data = path.read_bytes()
    if len(data) != remote.size:
        return False
    if remote.sha256 is not None:
        return hashlib.sha256(data).hexdigest() == remote.sha256
    blob = b"blob " + str(len(data)).encode() + b"\0" + data
    return hashlib.sha1(blob).hexdigest() == remote.git_oid


def fetch_case(case: str, raw_root: Path, fetcher: Fetcher) -> dict[str, str]:
    """Download one case into raw_root/case/, verifying every file.

    Returns {file name: sha256 of the local bytes}. A file already on disk is
    kept only if it matches the published hash; a mismatch after download
    raises ValueError and leaves no file behind.
    """
    case_dir = raw_root / case
    case_dir.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}
    for remote in fetcher.list_files(case):
        name = remote.path.rsplit("/", 1)[-1]
        dest = case_dir / name
        if not (dest.is_file() and _file_matches(dest, remote)):
            tmp = dest.with_name(name + ".part")
            fetcher.download(remote.path, tmp)
            if not _file_matches(tmp, remote):
                tmp.unlink(missing_ok=True)
                raise ValueError(f"{remote.path}: downloaded bytes do not match")
            os.replace(tmp, dest)
        checksums[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    return dict(sorted(checksums.items()))


# ── convert ──────────────────────────────────────────────────────────────────


class LeakageError(ValueError):
    """A label-carrying string would reach a pipeline input."""


@dataclass
class ConvertedCase:
    incident_id: str
    record: CaseRecord
    candidate_services: list[str]
    root_cause: str  # canonical
    row_counts: dict[str, int]
    trace_time_unit: str | None
    injection_signatures: dict[str, int]
    seal_path: Path
    notes: list[str] = field(default_factory=list)


def _metric_services(columns: Iterable[str]) -> list[str]:
    return sorted({c.split("_", 1)[0] for c in columns if c != "time" and "_" in c})


def _write_metrics(df: pd.DataFrame, system: str, path: Path) -> int:
    long = df.melt(id_vars="time", var_name="column", value_name="value").dropna()
    split = long["column"].str.split("_", n=1, expand=True)
    if split.shape[1] < 2 or split[1].isna().any():
        raise ValueError("metric column without a <service>_<metric> name")
    services = split[0].map(lambda s: canonical(system, s))
    table = pa.table(
        {
            "timestamp": long["time"].astype("float64").to_numpy(),
            "metric_name": split[1].to_numpy(),
            "value": long["value"].astype("float64").to_numpy(),
            "labels": [json.dumps({"service_name": s}) for s in services],
        }
    )
    pq.write_table(table, path)
    return int(table.num_rows)


def _microsecond_factor(values: pd.Series) -> tuple[int, str]:
    magnitude = float(values.abs().median())
    for threshold, factor, unit in _TO_MICROSECONDS:
        if magnitude >= threshold:
            return factor, unit
    raise ValueError(f"trace startTime magnitude {magnitude:g} is not an epoch time")


def _to_us(values: pd.Series, factor: int) -> Any:
    ints = values.astype("int64")
    return (ints // -factor if factor < 0 else ints * factor).to_numpy()


def _write_traces(df: pd.DataFrame, system: str, path: Path) -> tuple[int, str]:
    factor, unit = _microsecond_factor(df["startTime"])
    operation = df["operationName"].fillna("")
    if "methodName" in df.columns:
        operation = df["methodName"].fillna(operation)
    table = pa.table(
        {
            "trace_id": df["traceID"].astype(str).to_numpy(),
            "span_id": df["spanID"].astype(str).to_numpy(),
            "parent_span_id": df["parentSpanID"].fillna("").astype(str).to_numpy(),
            "operation_name": operation.astype(str).to_numpy(),
            "service_name": [canonical(system, s) for s in df["serviceName"]],
            "start_time_us": _to_us(df["startTime"], factor),
            "duration_us": _to_us(df["duration"], factor),
            "status_code": df["statusCode"].fillna("").astype(str).to_numpy(),
        }
    )
    pq.write_table(table, path)
    return int(table.num_rows), unit


def _write_logs(df: pd.DataFrame, system: str, path: Path) -> int:
    stamps = pd.to_datetime(df["timestamp"].astype("int64"), unit="s", utc=True)
    n = len(df)
    table = pa.table(
        {
            "timestamp": stamps.dt.strftime("%Y-%m-%dT%H:%M:%SZ").to_numpy(),
            "service_name": [canonical(system, s) for s in df["container_name"]],
            "severity": [""] * n,
            "body": df["message"].fillna("").astype(str).to_numpy(),
            "trace_id": [""] * n,
            "span_id": [""] * n,
        }
    )
    pq.write_table(table, path)
    return int(table.num_rows)


def _iso(epoch_s: float) -> str:
    return datetime.fromtimestamp(epoch_s, tz=UTC).isoformat()


def leakage_findings(case_dir: Path, record: CaseRecord) -> dict[str, int]:
    """Count label-carrying strings in everything a pipeline can read.

    Keys starting with ``forbidden:`` must all be zero for a case to be
    sealed; ``signature:`` keys count fault-injection tool strings in log
    bodies (covariate, not an error).
    """
    findings: dict[str, int] = {}
    texts: list[str] = [p.name for p in case_dir.iterdir()]
    manifest = case_dir / "manifest.json"
    manifest_text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
    texts.append(manifest_text)
    bodies: list[str] = []
    for parquet in sorted(case_dir.glob("*.parquet")):
        table = pq.read_table(parquet)
        for name in table.column_names:
            column = table.column(name)
            if pa.types.is_string(column.type) or pa.types.is_large_string(column.type):
                values = [v for v in column.to_pylist() if v]
                texts.extend(values)
                if parquet.name.startswith("p3_") and name == "body":
                    bodies.extend(values)
    blob = "\n".join(texts)
    lowered = blob.lower()
    findings["forbidden:case_name"] = lowered.count(record.case.lower())
    findings["forbidden:case_name_pattern"] = len(_CASE_NAME.findall(blob))
    findings["forbidden:inject_time_in_manifest"] = manifest_text.count(
        str(record.inject_time)
    )
    body_text = "\n".join(bodies).lower()
    for sig in _INJECTION_SIGNATURES:
        findings[f"signature:{sig}"] = body_text.count(sig)
    return findings


def convert_case(
    record: CaseRecord,
    raw_dir: Path,
    out_root: Path,
    corpus: str,
    *,
    seal_key: bytes,
    variant_config_hash: str,
    root: Path | None = None,
) -> ConvertedCase:
    """Convert one fetched case, scan it for leakage, then seal it.

    out_root is repo-relative (e.g. data/rcaeval/pool) so that the paths in
    the window — and therefore window_hash — are the same on every machine.
    Files are written under ``root / out_root`` when root is given (the CLI
    passes the repository root, so it never depends on the working
    directory), else under out_root itself. Refuses to overwrite an existing
    incident directory.
    """
    incident_id = opaque_id(record.case, corpus)
    rel_dir = out_root / incident_id  # as written into the window
    case_dir = rel_dir if root is None else root / rel_dir
    if case_dir.exists():
        raise FileExistsError(f"{case_dir} exists; converted cases are write-once")
    case_dir.mkdir(parents=True)
    system = record.system
    notes: list[str] = []

    metrics = pd.read_parquet(raw_dir / "metrics.parquet")
    p1 = case_dir / "p1_metrics.parquet"
    counts = {"p1_metrics": _write_metrics(metrics, system, p1)}
    modal_names: list[Iterable[str]] = [_metric_services(metrics.columns)]

    p2: Path | None = None
    unit: str | None = None
    traces_file = raw_dir / "traces.parquet"
    if traces_file.is_file():
        traces = pd.read_parquet(traces_file)
        p2 = case_dir / "p2_traces.parquet"
        counts["p2_traces"], unit = _write_traces(traces, system, p2)
        modal_names.append(traces["serviceName"].dropna().unique())
    elif record.has_traces:
        notes.append("traces listed in the index but no traces.parquet")

    p3: Path | None = None
    logs_file = raw_dir / "logs.parquet"
    if logs_file.is_file():
        logs = pd.read_parquet(logs_file)
        if len(logs):
            p3 = case_dir / "p3_logs.parquet"
            counts["p3_logs"] = _write_logs(logs, system, p3)
            modal_names.append(logs["container_name"].dropna().unique())
    if p3 is None:
        notes.append("logs_missing")

    candidates = candidate_set(system, *modal_names)
    root_cause = canonical(system, record.root_cause_service)
    if root_cause not in candidates:
        raise ValueError(
            f"{incident_id}: ground-truth service is not in the candidate set; "
            "the case could never be scored correctly"
        )

    times = metrics["time"].astype("float64")
    window = TelemetryWindow(
        incident_id=incident_id,
        variant_config_hash=variant_config_hash,
        window_start_iso=_iso(float(times.min())),
        window_end_iso=_iso(float(times.max())),
        evaluation_phase=CORPORA[corpus][2],
        p1_metrics_path=str(rel_dir / p1.name),
        p2_traces_path=None if p2 is None else str(rel_dir / p2.name),
        p3_logs_path=None if p3 is None else str(rel_dir / p3.name),
        schema_version=MANIFEST_SCHEMA_VERSION,
    )
    (case_dir / "manifest.json").write_text(
        json.dumps(
            {**window.model_dump(), "window_hash": window.compute_window_hash()},
            indent=2,
        ),
        encoding="utf-8",
    )

    findings = leakage_findings(case_dir, record)
    leaks = {k: v for k, v in findings.items() if k.startswith("forbidden:") and v}
    if leaks:
        raise LeakageError(f"{incident_id}: label-carrying strings found {leaks}")
    seal_path = write_seal(case_dir, window, seal_key, base=root)
    return ConvertedCase(
        incident_id=incident_id,
        record=record,
        candidate_services=candidates,
        root_cause=root_cause,
        row_counts=counts,
        trace_time_unit=unit,
        injection_signatures={
            k.split(":", 1)[1]: v
            for k, v in findings.items()
            if k.startswith("signature:")
        },
        seal_path=seal_path,
        notes=notes,
    )


# ── ground truth and corpus manifest ─────────────────────────────────────────


def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_once(path: Path, document: dict[str, Any]) -> Path:
    text = json.dumps(document, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == text:
            return path
        raise FileExistsError(f"{path} exists with different content; it is write-once")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def write_ground_truth(
    converted: Iterable[ConvertedCase],
    path: Path,
    corpus: str,
    key: bytes,
    raw_checksums: dict[str, dict[str, str]],
) -> Path:
    """Signed ground truth: the only place a case name meets its opaque ID.

    Also holds the SHA-256 of each downloaded file: anyone can hash the public
    files, so those hashes identify the case and belong here, not in the
    label-free corpus manifest.
    """
    cases = {
        c.incident_id: {
            "case": c.record.case,
            "dataset": c.record.dataset,
            "system": c.record.system,
            "root_cause_service": c.root_cause,
            "root_cause_service_raw": c.record.root_cause_service,
            "fault": c.record.fault,
            "repetition": c.record.repetition,
            "inject_time": c.record.inject_time,
            "candidate_services": c.candidate_services,
            "raw_sha256": raw_checksums[c.record.case],
            "covariates": {
                "logs_missing": "logs_missing" in c.notes,
                "injection_signatures": c.injection_signatures,
            },
        }
        for c in sorted(converted, key=lambda c: c.incident_id)
    }
    body = {
        "kind": "rcaeval-ground-truth",
        "corpus": corpus,
        "dataset_repo": HF_REPO,
        "dataset_revision": HF_REVISION,
        "cases": cases,
    }
    signature = hmac.new(key, _canonical_bytes(body), hashlib.sha256).hexdigest()
    return _write_once(path, {**body, "signature": signature})


def verify_ground_truth(path: Path, key: bytes) -> dict[str, Any]:
    """Return the ground-truth cases, or raise ValueError if the file was altered."""
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = str(document.pop("signature", ""))
    expected = hmac.new(key, _canonical_bytes(document), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(claimed, expected):
        raise ValueError(f"{path}: ground-truth signature does not verify")
    cases: dict[str, Any] = document["cases"]
    return cases


def write_corpus_manifest(
    converted: Iterable[ConvertedCase], path: Path, corpus: str
) -> tuple[Path, str]:
    """Label-free corpus manifest; returns its path and digest.

    ``case_order`` (sorted opaque IDs) is the frozen order that
    helios.research.seeds.run_seed uses. The digest is SHA-256 over the
    canonical JSON of everything else and is what the tracker records.
    """
    items = sorted(converted, key=lambda c: c.incident_id)
    body = {
        "kind": "rcaeval-corpus-manifest",
        "corpus": corpus,
        "evaluation_phase": str(CORPORA[corpus][2]),
        "dataset_repo": HF_REPO,
        "dataset_revision": HF_REVISION,
        "opaque_id_seed_slot": CORPORA[corpus][1],
        "case_order": [c.incident_id for c in items],
        "cases": {
            c.incident_id: {
                "seal_sha256": hashlib.sha256(c.seal_path.read_bytes()).hexdigest(),
                "streams": sorted(c.row_counts),
            }
            for c in items
        },
    }
    digest = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    return _write_once(path, {**body, "manifest_digest": digest}), digest
