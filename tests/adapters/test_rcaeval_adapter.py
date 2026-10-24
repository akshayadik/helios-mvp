"""Tests for the RCAEval adapter (S1.1): names, opaque IDs, fetch checks,
conversion, leakage scan, sealing, ground truth, corpus manifest, pool lock.

All data is synthetic; nothing touches the network or the real pool.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow.parquet as pq
import pytest

from helios.adapters import names
from helios.adapters.rcaeval import (
    CaseRecord,
    ConvertedCase,
    LeakageError,
    RemoteFile,
    convert_case,
    fetch_case,
    leakage_findings,
    load_index,
    opaque_id,
    select_corpus,
    verify_ground_truth,
    write_corpus_manifest,
    write_ground_truth,
)
from helios.schemas.telemetry import TelemetryWindow
from helios.telemetry import pool_lock
from helios.telemetry.reader import CaptureReader
from helios.telemetry.seal import check_seal
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"k" * 32
T0 = 1_700_000_000  # epoch seconds
CONFIG_HASH = "f" * 64


def _record(case: str = "re2ob_checkoutservice_cpu_1", **kw: object) -> CaseRecord:
    base: dict[str, object] = {
        "case": case,
        "dataset": case.split("_", 1)[0],
        "system": case[3:5],
        "root_cause_service": "checkoutservice",
        "fault": "cpu",
        "repetition": 1,
        "inject_time": T0 + 60,
        "has_logs": True,
        "has_traces": True,
    }
    base.update(kw)
    return CaseRecord(**base)  # type: ignore[arg-type]


def _raw_case(
    tmp: Path, *, logs: bool = True, traces: bool = True, body: str = "GET /cart 200"
) -> Path:
    raw = tmp / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    times = [T0 + i for i in range(120)]
    pd.DataFrame(
        {
            "time": times,
            "checkoutservice_cpu": [float(i % 7) for i in range(120)],
            "frontend_latency-90": [float(i % 5) for i in range(120)],
            "redis-cart_mem": [float(i % 3) for i in range(120)],
        }
    ).to_parquet(raw / "metrics.parquet")
    if traces:
        pd.DataFrame(
            {
                "traceID": ["t1", "t1"],
                "spanID": ["s1", "s2"],
                "parentSpanID": [None, "s1"],
                "serviceName": ["frontendservice", "checkoutservice"],
                "methodName": [None, "PlaceOrder"],
                "operationName": ["GET /cart", "grpc"],
                "startTime": [(T0 + 10) * 1_000_000, (T0 + 11) * 1_000_000],
                "duration": [5_000, 2_000],
                "statusCode": ["OK", None],
            }
        ).to_parquet(raw / "traces.parquet")
    if logs:
        pd.DataFrame(
            {
                "timestamp": pd.array([T0 + 5, T0 + 6], dtype="Int64"),
                "container_name": ["frontend", "checkoutservice"],
                "message": [body, "order placed"],
            }
        ).to_parquet(raw / "logs.parquet")
    return raw


def _convert(
    tmp: Path, record: CaseRecord | None = None, **raw_kw: Any
) -> ConvertedCase:
    raw = _raw_case(tmp, **raw_kw)
    return convert_case(
        record or _record(),
        raw,
        tmp / "build",
        "build",
        seal_key=KEY,
        variant_config_hash=CONFIG_HASH,
    )


# ── names ────────────────────────────────────────────────────────────────────


def test_canonical_applies_the_alias_table_and_lowercases() -> None:
    assert names.canonical("ob", "FrontendService") == "frontend"
    assert names.canonical("tt", "ts-auth-service") == "ts-auth-service"


def test_canonical_rejects_an_unknown_system() -> None:
    with pytest.raises(ValueError, match="unknown system"):
        names.canonical("xx", "a")


def test_candidate_set_is_the_union_over_modalities() -> None:
    got = names.candidate_set("ob", ["frontend", "cart"], ["frontendservice"], ["cart"])
    assert got == ["cart", "frontend"]


def test_unresolved_alias_pair_stops_sealing() -> None:
    with pytest.raises(names.UnresolvedAliasError, match="cart"):
        names.candidate_set("ss", ["cart", "cart-service"])


# ── opaque IDs and index ─────────────────────────────────────────────────────


def test_opaque_id_is_deterministic_hex_and_carries_no_label() -> None:
    case = "re2ob_checkoutservice_cpu_1"
    a, b = opaque_id(case, "pool"), opaque_id(case, "pool")
    assert a == b and len(a) == 32 and int(a, 16) >= 0
    assert opaque_id(case, "build") != a
    assert "checkout" not in a and "cpu" not in a


def test_load_index_and_select_corpus(tmp_path: Path) -> None:
    rows = [
        {
            "case": c,
            "system": c[3:5],
            "root_cause_service": "x",
            "fault": "cpu",
            "repetition": 1,
            "inject_time": T0,
            "has_logs": True,
            "has_traces": False,
        }
        for c in ("re2ss_x_cpu_1", "re2ob_x_cpu_1", "re1tt_x_cpu_1")
    ]
    path = tmp_path / "cases.parquet"
    pd.DataFrame(rows).to_parquet(path)
    records = load_index(path)
    assert [r.case for r in records] == sorted(str(r["case"]) for r in rows)
    assert [r.case for r in select_corpus(records, "pool")] == ["re2ob_x_cpu_1"]
    assert {r.case for r in select_corpus(records, "build")} == {
        "re1tt_x_cpu_1",
        "re2ss_x_cpu_1",
    }


# ── fetch ────────────────────────────────────────────────────────────────────


class FakeFetcher:
    def __init__(self, files: dict[str, bytes], corrupt: bool = False) -> None:
        self.files = files
        self.corrupt = corrupt
        self.downloads = 0

    def list_files(self, case: str) -> list[RemoteFile]:
        out = []
        for path, data in self.files.items():
            lfs = path.endswith(".parquet")
            blob = b"blob " + str(len(data)).encode() + b"\0" + data
            out.append(
                RemoteFile(
                    path=path,
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest() if lfs else None,
                    git_oid=hashlib.sha1(blob).hexdigest(),
                )
            )
        return out

    def download(self, path: str, dest: Path) -> None:
        self.downloads += 1
        data = self.files[path]
        dest.write_bytes(data + b"x" if self.corrupt else data)


def test_fetch_verifies_lfs_and_git_blob_hashes(tmp_path: Path) -> None:
    files = {"c/metrics.parquet": b"PAR1data", "c/inject_time.txt": b"1700000060"}
    fetcher = FakeFetcher(files)
    sums = fetch_case("c", tmp_path, fetcher)
    assert sums == {
        name.split("/")[1]: hashlib.sha256(data).hexdigest()
        for name, data in files.items()
    }
    # A second fetch reuses verified files.
    fetch_case("c", tmp_path, fetcher)
    assert fetcher.downloads == 2


def test_fetch_rejects_corrupted_download_and_leaves_no_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="do not match"):
        fetch_case("c", tmp_path, FakeFetcher({"c/a.parquet": b"abc"}, corrupt=True))
    assert list((tmp_path / "c").iterdir()) == []


# ── convert ──────────────────────────────────────────────────────────────────


def test_convert_writes_helios_streams_with_normalised_names(tmp_path: Path) -> None:
    out = _convert(tmp_path)
    case_dir = tmp_path / "build" / out.incident_id
    p1 = pq.read_table(case_dir / "p1_metrics.parquet").to_pandas()
    p2 = pq.read_table(case_dir / "p2_traces.parquet").to_pandas()
    p3 = pq.read_table(case_dir / "p3_logs.parquet").to_pandas()
    assert list(p1.columns) == ["timestamp", "metric_name", "value", "labels"]
    assert set(p1["metric_name"]) == {"cpu", "latency-90", "mem"}
    assert {json.loads(x)["service_name"] for x in p1["labels"]} == {
        "checkoutservice",
        "frontend",
        "redis-cart",
    }
    assert list(p2["service_name"]) == ["frontend", "checkoutservice"]
    assert list(p2["start_time_us"]) == [(T0 + 10) * 1_000_000, (T0 + 11) * 1_000_000]
    assert list(p2["operation_name"]) == ["GET /cart", "PlaceOrder"]
    assert p3["timestamp"].iloc[0].endswith("Z")
    assert out.trace_time_unit == "us"
    assert out.candidate_services == ["checkoutservice", "frontend", "redis-cart"]
    assert out.root_cause == "checkoutservice"
    assert out.notes == []


def test_converted_case_is_sealed_and_readable(tmp_path: Path) -> None:
    out = _convert(tmp_path)
    case_dir = tmp_path / "build" / out.incident_id
    raw = json.loads((case_dir / "manifest.json").read_text())
    raw.pop("window_hash")
    assert check_seal(case_dir, TelemetryWindow(**raw), KEY) is None
    verification = CaptureReader(tmp_path / "build", seal_key=KEY).read(out.incident_id)
    assert verification.intact


def test_seconds_trace_times_are_converted_to_microseconds(tmp_path: Path) -> None:
    raw = _raw_case(tmp_path)
    df = pd.read_parquet(raw / "traces.parquet")
    df["startTime"] = [T0 + 10, T0 + 11]
    df["duration"] = [1, 2]
    df.to_parquet(raw / "traces.parquet")
    out = convert_case(
        _record(),
        raw,
        tmp_path / "build",
        "build",
        seal_key=KEY,
        variant_config_hash=CONFIG_HASH,
    )
    p2 = pq.read_table(tmp_path / "build" / out.incident_id / "p2_traces.parquet")
    assert out.trace_time_unit == "s"
    assert p2.column("duration_us").to_pylist() == [1_000_000, 2_000_000]


def test_missing_logs_and_traces_are_recorded_not_imputed(tmp_path: Path) -> None:
    out = _convert(tmp_path, logs=False, traces=False)
    raw = json.loads(
        (tmp_path / "build" / out.incident_id / "manifest.json").read_text()
    )
    assert raw["p2_traces_path"] is None and raw["p3_logs_path"] is None
    assert "logs_missing" in out.notes
    assert "traces listed in the index but no traces.parquet" in out.notes


def test_root_cause_outside_candidate_set_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not in the candidate set"):
        _convert(tmp_path, record=_record(root_cause_service="paymentservice"))


def test_case_name_in_any_input_blocks_sealing(tmp_path: Path) -> None:
    with pytest.raises(LeakageError, match="case_name"):
        _convert(tmp_path, body="chaos run re2ob_checkoutservice_cpu_1 started")
    case_dirs = list((tmp_path / "build").iterdir())
    assert not (case_dirs[0] / "content_seal.json").exists()


def test_injection_tool_strings_are_counted_as_covariate(tmp_path: Path) -> None:
    out = _convert(tmp_path, body="stress-ng: dispatching hogs")
    assert out.injection_signatures["stress-ng"] == 1
    assert out.injection_signatures["chaos"] == 0


def test_leakage_scan_finds_inject_time_in_manifest(tmp_path: Path) -> None:
    case_dir = tmp_path / "x"
    case_dir.mkdir()
    (case_dir / "manifest.json").write_text(json.dumps({"t": T0 + 60}))
    findings = leakage_findings(case_dir, _record())
    assert findings["forbidden:inject_time_in_manifest"] == 1


def test_conversion_is_write_once(tmp_path: Path) -> None:
    _convert(tmp_path)
    with pytest.raises(FileExistsError, match="write-once"):
        _convert(tmp_path)


def test_window_paths_are_relative_to_the_given_root(tmp_path: Path) -> None:
    out = _convert(tmp_path)
    raw = json.loads(
        (tmp_path / "build" / out.incident_id / "manifest.json").read_text()
    )
    assert raw["p1_metrics_path"] == str(
        tmp_path / "build" / out.incident_id / "p1_metrics.parquet"
    )
    assert raw["evaluation_phase"] == "exploratory"


# ── ground truth and manifest ────────────────────────────────────────────────


def test_ground_truth_is_signed_write_once_and_tamper_evident(tmp_path: Path) -> None:
    out = _convert(tmp_path)
    sums = {out.record.case: {"metrics.parquet": "ab"}}
    path = tmp_path / "gt.json"
    write_ground_truth([out], path, "build", KEY, sums)
    write_ground_truth([out], path, "build", KEY, sums)  # identical: allowed
    cases = verify_ground_truth(path, KEY)
    assert cases[out.incident_id]["case"] == out.record.case
    assert cases[out.incident_id]["inject_time"] == T0 + 60
    with pytest.raises(FileExistsError):
        write_ground_truth([out], path, "build", KEY, {out.record.case: {}})
    doc = json.loads(path.read_text())
    doc["cases"][out.incident_id]["root_cause_service"] = "frontend"
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="does not verify"):
        verify_ground_truth(path, KEY)


def test_corpus_manifest_is_label_free_with_sorted_case_order(tmp_path: Path) -> None:
    a = _convert(tmp_path / "a", record=_record("re2ob_checkoutservice_cpu_1"))
    b = _convert(tmp_path / "b", record=_record("re2ob_checkoutservice_cpu_2"))
    path, digest = write_corpus_manifest([b, a], tmp_path / "m.json", "build")
    doc = json.loads(path.read_text())
    assert doc["case_order"] == sorted([a.incident_id, b.incident_id])
    claimed = doc.pop("manifest_digest")
    body = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    assert claimed == digest == hashlib.sha256(body).hexdigest()
    text = path.read_text()
    assert "checkout" not in text and "re2ob" not in text and str(T0 + 60) not in text


# ── pool lock ────────────────────────────────────────────────────────────────


def _git_repo(path: Path) -> Path:
    path.mkdir()
    run = {"cwd": path, "check": True, "capture_output": True}
    subprocess.run(["git", "init", "-q"], **run)  # type: ignore[call-overload]
    subprocess.run(  # type: ignore[call-overload]
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        **run,
    )
    return path


def test_pool_is_locked_until_the_build_freeze_tag(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    assert not pool_lock.build_frozen(repo)
    with pytest.raises(pool_lock.PoolLockedError, match="build-freeze"):
        pool_lock.require_unlocked("abc", repo)
    subprocess.run(["git", "tag", "build-freeze"], cwd=repo, check=True)
    assert pool_lock.build_frozen(repo)
    pool_lock.require_unlocked("abc", repo)


def test_reader_refuses_confirmatory_windows_while_locked(tmp_path: Path) -> None:
    raw = _raw_case(tmp_path)
    out = convert_case(
        _record(),
        raw,
        tmp_path / "pool",
        "pool",
        seal_key=KEY,
        variant_config_hash=CONFIG_HASH,
    )

    def locked(incident_id: str) -> None:
        raise pool_lock.PoolLockedError(incident_id)

    with pytest.raises(pool_lock.PoolLockedError):
        CaptureReader(tmp_path / "pool", KEY, pool_lock=locked).read(out.incident_id)
    unlocked = CaptureReader(tmp_path / "pool", KEY, pool_lock=lambda _id: None)
    assert unlocked.read(out.incident_id).intact


def test_build_frozen_checks_this_repository_by_default() -> None:
    assert isinstance(pool_lock.build_frozen(), bool)
