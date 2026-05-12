# HMAC-Chained Audit Ledgers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract HMAC chain logic into a shared `HMACChainedLog` base class, refactor `DeviationLog` to subclass it, implement a complete `ExclusionLedger`, and fix filename discrepancies in two tracking documents.

**Architecture:** `helios/vcl/hmac_chain.py` holds `HMACChainedLog` (chain append + verify + `_post_sign_fields` hook). `bin/log_deviation.py` defines `DeviationLog(HMACChainedLog)` with §B.12 fields plus `deviation_id` post-sign. `bin/log_exclusion.py` defines `ExclusionLedger(HMACChainedLog)` with §3.6.8 runtime fields. Both CLI scripts preserve their existing invocation signatures exactly.

**Tech Stack:** Python 3.11, stdlib `hmac` / `hashlib` / `json` / `datetime`, pytest, ruff, mypy strict.

**Spec:** `docs/superpowers/specs/2026-05-12-hmac-chained-ledgers-design.md`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `helios/vcl/hmac_chain.py` | `HMACChainedLog` base class + `GENESIS` constant |
| Create | `tests/test_hmac_chain.py` | Base class unit tests |
| Modify | `bin/log_deviation.py` | Refactor: `DeviationLog(HMACChainedLog)` + `load_key()` + CLI |
| Modify | `tests/test_deviation_log.py` | Refactor to class API + add `test_schema` |
| Modify | `bin/log_exclusion.py` | Implement: `ExclusionLedger(HMACChainedLog)` + CLI |
| Create | `tests/test_exclusion_ledger.py` | `test_append` + HMAC chain + schema tests |
| Modify | `docs/tracking/HELIOS_MVP_Execution_plan_v0.6.md` | Fix `eval/deviation_log.py` → `bin/log_deviation.py` |
| Modify | `docs/tracking/helios_mvp_tracking.md` | Clarify filenames in S0-D2-ENG01 and ENG02 Notes |

---

## Task 1: `helios/vcl/hmac_chain.py` — HMACChainedLog base class

**Files:**
- Create: `helios/vcl/hmac_chain.py`
- Create: `tests/test_hmac_chain.py`

- [ ] **Step 1.1: Write the failing tests**

Create `tests/test_hmac_chain.py`:

```python
"""Unit tests for HMACChainedLog base class."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from helios.vcl.hmac_chain import GENESIS, HMACChainedLog

_KEY = b"test-secret-of-at-least-32-characters-x"


class _ConcreteLog(HMACChainedLog):
    REQUIRED_FIELDS = ("msg",)


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "test.jsonl"


@pytest.fixture
def log(log_path: Path) -> _ConcreteLog:
    return _ConcreteLog(key=_KEY, log_path=log_path)


def test_genesis_on_missing_file(log: _ConcreteLog) -> None:
    assert log.previous_signature() == GENESIS


def test_genesis_on_empty_file(log: _ConcreteLog, log_path: Path) -> None:
    log_path.write_text("", encoding="utf-8")
    assert log.previous_signature() == GENESIS


def test_genesis_on_whitespace_only_file(log: _ConcreteLog, log_path: Path) -> None:
    log_path.write_text("   \n\n   \n", encoding="utf-8")
    assert log.previous_signature() == GENESIS


def test_signature_excludes_signature_field(log: _ConcreteLog) -> None:
    entry_with_sig = {"msg": "hello", "signature": "abc", "prev_signature": GENESIS}
    entry_without_sig = {"msg": "hello", "prev_signature": GENESIS}
    assert log.compute_signature(entry_with_sig) == log.compute_signature(entry_without_sig)


def test_signature_excludes_deviation_id_field(log: _ConcreteLog) -> None:
    base = {"msg": "hello", "prev_signature": GENESIS}
    with_id = {**base, "deviation_id": "abc123"}
    assert log.compute_signature(base) == log.compute_signature(with_id)


def test_short_key_raises_at_construction(log_path: Path) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        _ConcreteLog(key=b"tooshort", log_path=log_path)


def test_append_missing_required_field_raises(log: _ConcreteLog) -> None:
    with pytest.raises(ValueError, match="Missing required fields"):
        log.append({})


def test_append_writes_valid_jsonl(log: _ConcreteLog, log_path: Path) -> None:
    log.append({"msg": "hello"})
    log.append({"msg": "world"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


def test_verify_passes_on_clean_log(log: _ConcreteLog) -> None:
    log.append({"msg": "a"})
    log.append({"msg": "b"})
    ok, msg = log.verify()
    assert ok, msg


def test_verify_fails_on_tampered_entry(log: _ConcreteLog, log_path: Path) -> None:
    log.append({"msg": "a"})
    log.append({"msg": "b"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["msg"] = "TAMPERED"
    lines[0] = json.dumps(entry, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _ = log.verify()
    assert not ok


def test_verify_empty_log_is_valid(log: _ConcreteLog) -> None:
    ok, msg = log.verify()
    assert ok
    assert "vacuously" in msg
```

- [ ] **Step 1.2: Run to confirm import fails**

```bash
poetry run pytest tests/test_hmac_chain.py -v
```

Expected: `ModuleNotFoundError: No module named 'helios.vcl.hmac_chain'`

- [ ] **Step 1.3: Implement `helios/vcl/hmac_chain.py`**

```python
"""HMAC-SHA256 chained append-only JSONL — C1 audit base for deviation log and exclusion ledger."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

GENESIS = "GENESIS"
_UNSIGNED_KEYS: frozenset[str] = frozenset({"signature", "deviation_id"})


class HMACChainedLog:
    """Append-only JSONL with HMAC-SHA256 chain integrity.

    Subclasses set REQUIRED_FIELDS to add domain field validation.
    Post-sign convenience fields are excluded from the signed payload via
    _UNSIGNED_KEYS. Override _post_sign_fields() to add them.
    """

    REQUIRED_FIELDS: tuple[str, ...] = ()

    def __init__(self, key: bytes, log_path: Path) -> None:
        if len(key) < 32:
            raise ValueError(f"HMAC key must be at least 32 bytes (got {len(key)}).")
        self._key = key
        self._path = log_path

    def previous_signature(self) -> str:
        """Return the last entry's signature, or GENESIS if file is empty/missing."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return GENESIS
        last = ""
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    last = stripped
        if not last:
            return GENESIS
        return str(json.loads(last)["signature"])

    def compute_signature(self, entry: dict[str, Any]) -> str:
        """HMAC-SHA256 over canonical JSON of entry, excluding _UNSIGNED_KEYS."""
        payload_dict = {k: v for k, v in entry.items() if k not in _UNSIGNED_KEYS}
        payload = json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def _post_sign_fields(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Override in subclasses to append post-sign convenience fields before writing."""
        return entry

    def append(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Validate required fields, build signed envelope, append JSONL line."""
        if missing := [f for f in self.REQUIRED_FIELDS if not fields.get(f)]:
            raise ValueError(f"Missing required fields: {missing}")
        prev_sig = self.previous_signature()
        entry: dict[str, Any] = {
            "timestamp_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
            "commit_sha": os.getenv("GITHUB_SHA", "LOCAL"),
            "prev_signature": prev_sig,
            **fields,
        }
        entry["signature"] = self.compute_signature(entry)
        entry = self._post_sign_fields(entry)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify(self) -> tuple[bool, str]:
        """Walk the chain from genesis; return (ok, message)."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return True, "Empty log — vacuously valid."
        expected_prev = GENESIS
        with self._path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                entry = json.loads(stripped)
                if entry.get("prev_signature") != expected_prev:
                    got = entry.get("prev_signature", "")[:12]
                    return False, (
                        f"Line {lineno}: prev_signature mismatch "
                        f"(expected {expected_prev[:12]}..., got {got}...)"
                    )
                recomputed = self.compute_signature(entry)
                if recomputed != entry.get("signature"):
                    return (
                        False,
                        f"Line {lineno}: signature does not verify (entry tampered).",
                    )
                expected_prev = entry["signature"]
        return True, "Chain verified."
```

- [ ] **Step 1.4: Run tests — all must pass**

```bash
poetry run pytest tests/test_hmac_chain.py -v
```

Expected: 11 tests pass.

- [ ] **Step 1.5: Commit**

```bash
git add helios/vcl/hmac_chain.py tests/test_hmac_chain.py
git commit -m "feat(vcl): add HMACChainedLog base class with full test suite"
```

---

## Task 2: Refactor `bin/log_deviation.py`

**Files:**
- Modify: `bin/log_deviation.py`
- Modify: `tests/test_deviation_log.py`

- [ ] **Step 2.1: Rewrite `tests/test_deviation_log.py`**

Replace the entire file with the refactored version below. The module is still loaded via importlib (preserving the existing pattern for bin/ scripts); fixtures now use direct key injection — no env monkeypatching for core chain tests.

```python
"""HMAC chain integrity tests for bin/log_deviation.py (§B.12)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent.parent


def _load_log_deviation_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "log_deviation", _HERE / "bin" / "log_deviation.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["log_deviation"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


log_deviation = _load_log_deviation_module()

_KEY = b"test-secret-of-at-least-32-characters-x"
_FIELDS: dict[str, str] = {
    "stage": "Stage 0",
    "clause": "§test",
    "change": "test change",
    "reason": "test reason",
    "analytic_consequence": "test consequence",
}


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "deviation_log.jsonl"


@pytest.fixture
def log(log_path: Path) -> Any:
    return log_deviation.DeviationLog(key=_KEY, log_path=log_path)


# ── Schema test (tracking ref: tests/test_deviation_log.py::test_schema) ──────

def test_schema(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    required = {
        "timestamp_utc", "commit_sha", "prev_signature",
        "stage", "clause", "change", "reason", "analytic_consequence",
        "signature", "deviation_id",
    }
    assert required <= set(entry.keys())
    assert entry["timestamp_utc"].endswith("Z")
    assert len(entry["signature"]) == 64
    int(entry["signature"], 16)  # must parse as hex
    assert entry["prev_signature"] == log_deviation.GENESIS
    assert entry["deviation_id"] == entry["signature"][:16]


# ── Required field validation ──────────────────────────────────────────────────

def test_missing_required_field_raises(log: Any) -> None:
    with pytest.raises(ValueError, match="Missing required fields"):
        log.append({"stage": "Stage 0"})  # missing clause, change, reason, analytic_consequence


# ── Chain integrity ────────────────────────────────────────────────────────────

def test_first_entry_has_genesis_prev_signature(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    assert entry["prev_signature"] == log_deviation.GENESIS
    assert len(entry["signature"]) == 64


def test_signature_is_64_hex_chars(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    assert len(entry["signature"]) == 64
    int(entry["signature"], 16)


def test_chain_links_correctly_across_three_entries(log: Any) -> None:
    e1 = log.append({**_FIELDS, "change": "first"})
    e2 = log.append({**_FIELDS, "change": "second"})
    e3 = log.append({**_FIELDS, "change": "third"})
    assert e2["prev_signature"] == e1["signature"]
    assert e3["prev_signature"] == e2["signature"]


def test_signature_recomputes_to_same_value(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    assert log.compute_signature(entry) == entry["signature"]


def test_tampered_change_field_breaks_signature(log: Any) -> None:
    entry = log.append(_FIELDS.copy())
    tampered = dict(entry)
    tampered["change"] = "MALICIOUS"
    assert log.compute_signature(tampered) != entry["signature"]


def test_tampered_prev_signature_breaks_chain(log: Any) -> None:
    e1 = log.append({**_FIELDS, "change": "first"})
    e2 = log.append({**_FIELDS, "change": "second"})
    assert e2["prev_signature"] == e1["signature"]
    tampered = dict(e2)
    tampered["prev_signature"] = "0" * 64
    assert log.compute_signature(tampered) != e2["signature"]


# ── Verify ─────────────────────────────────────────────────────────────────────

def test_verify_chain_passes_on_clean_log(log: Any, log_path: Path) -> None:
    log.append({**_FIELDS, "change": "first"})
    log.append({**_FIELDS, "change": "second"})
    ok, msg = log.verify()
    assert ok, msg


def test_verify_chain_fails_on_tampered_log(log: Any, log_path: Path) -> None:
    log.append({**_FIELDS, "change": "first"})
    log.append({**_FIELDS, "change": "second"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["change"] = "MALICIOUS"
    lines[1] = json.dumps(second, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _ = log.verify()
    assert not ok


# ── Format ─────────────────────────────────────────────────────────────────────

def test_log_file_is_one_json_per_line(log: Any, log_path: Path) -> None:
    log.append({**_FIELDS, "change": "a"})
    log.append({**_FIELDS, "change": "b"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


# ── load_key() ─────────────────────────────────────────────────────────────────

def test_missing_secret_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(log_deviation.ENV_KEY, raising=False)
    with pytest.raises(SystemExit):
        log_deviation.load_key()


def test_short_secret_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(log_deviation.ENV_KEY, "too-short")
    with pytest.raises(SystemExit):
        log_deviation.load_key()


# ── Determinism ────────────────────────────────────────────────────────────────

def test_canonical_signature_is_deterministic(log: Any) -> None:
    entry = {
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "commit_sha": "abc",
        "prev_signature": log_deviation.GENESIS,
        "stage": "S",
        "clause": "C",
        "change": "X",
        "reason": "R",
        "analytic_consequence": "A",
    }
    sig = log.compute_signature(entry)
    assert sig == log.compute_signature(entry)
```

- [ ] **Step 2.2: Run to confirm tests fail**

```bash
poetry run pytest tests/test_deviation_log.py -v
```

Expected: most tests fail with `AttributeError: module 'log_deviation' has no attribute 'DeviationLog'` (the module still uses old function API).

- [ ] **Step 2.3: Rewrite `bin/log_deviation.py`**

Replace the entire file:

```python
#!/usr/bin/env python3
"""Append a signed deviation log entry to deviation_log.jsonl.

Each entry is HMAC-SHA256 chained: every entry's signature signs both its own
fields AND the previous entry's signature, so any tampering anywhere in the
chain invalidates every subsequent signature. The first entry's prev_signature
is the literal string "GENESIS".

Schema (§B.12):
    timestamp_utc:        ISO-8601 with Z suffix (UTC)
    commit_sha:           Git commit SHA ($GITHUB_SHA in CI, else "LOCAL")
    prev_signature:       Hex signature of preceding entry, or "GENESIS"
    stage:                Stage 0..8
    clause:               Section reference (e.g. "§3.6.6")
    change:               Concrete description of what changed
    reason:               Justification
    analytic_consequence: Which hypothesis/variant is affected
    signature:            HMAC-SHA256 hex over canonical JSON of all above fields
    deviation_id:         First 16 chars of signature (post-sign, not in payload)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from helios.vcl.hmac_chain import GENESIS as GENESIS  # re-export for tests
from helios.vcl.hmac_chain import HMACChainedLog

HELIOS_ENABLE_DEVIATION_LOG: bool = True  # always-on C1 audit infrastructure

LOG_FILE = Path("deviation_log.jsonl")
ENV_KEY = "DEVIATION_HMAC_SECRET"


def load_key() -> bytes:
    """Read the HMAC secret from $DEVIATION_HMAC_SECRET. Exit on failure."""
    key = os.getenv(ENV_KEY)
    if not key:
        sys.stderr.write(
            f"ERROR: {ENV_KEY} not set. Copy .env.example to .env and set a secret.\n"
        )
        sys.exit(2)
    if len(key) < 32:
        sys.stderr.write(
            f"ERROR: {ENV_KEY} must be at least 32 characters (got {len(key)}).\n"
        )
        sys.exit(2)
    return key.encode("utf-8")


class DeviationLog(HMACChainedLog):
    """HMAC-chained log for research protocol deviations (§B.12)."""

    REQUIRED_FIELDS = ("stage", "clause", "change", "reason", "analytic_consequence")

    def _post_sign_fields(self, entry: dict[str, Any]) -> dict[str, Any]:
        entry["deviation_id"] = entry["signature"][:16]
        return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd")

    parser.add_argument("--stage")
    parser.add_argument("--clause")
    parser.add_argument("--change")
    parser.add_argument("--reason")
    parser.add_argument("--analytic-consequence")

    sub.add_parser("verify", help="Verify the entire HMAC chain.")

    args = parser.parse_args()

    if args.cmd == "verify":
        ledger = DeviationLog(key=load_key(), log_path=LOG_FILE)
        ok, msg = ledger.verify()
        print(("✅ " if ok else "❌ ") + msg)
        return 0 if ok else 1

    required = ["stage", "clause", "change", "reason", "analytic_consequence"]
    missing = [r for r in required if not getattr(args, r, None)]
    if missing:
        flags = ", ".join("--" + m.replace("_", "-") for m in missing)
        parser.error(f"Missing required arguments: {flags}")

    fields = {
        "stage": args.stage,
        "clause": args.clause,
        "change": args.change,
        "reason": args.reason,
        "analytic_consequence": args.analytic_consequence,
    }
    ledger = DeviationLog(key=load_key(), log_path=LOG_FILE)
    entry = ledger.append(fields)
    print(f"✅ Deviation logged: {entry['clause']} | sig={entry['signature'][:12]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: `from helios.vcl.hmac_chain import GENESIS as GENESIS` uses the `as GENESIS` form to make the name visible as a module attribute (`log_deviation.GENESIS`) while also satisfying ruff's `F401` (re-export is intentional — tests rely on `log_deviation.GENESIS`).

- [ ] **Step 2.4: Run tests — all must pass**

```bash
poetry run pytest tests/test_deviation_log.py -v
```

Expected: 14 tests pass.

- [ ] **Step 2.5: Verify the existing deviation_log.jsonl chain is still intact**

```bash
set -a; source .env; set +a && poetry run python bin/log_deviation.py verify
```

Expected: `✅ Chain verified.`

- [ ] **Step 2.6: Commit**

```bash
git add bin/log_deviation.py tests/test_deviation_log.py
git commit -m "refactor(deviation-log): extract DeviationLog(HMACChainedLog), add test_schema"
```

---

## Task 3: Implement `bin/log_exclusion.py`

**Files:**
- Modify: `bin/log_exclusion.py`
- Create: `tests/test_exclusion_ledger.py`

- [ ] **Step 3.1: Write the failing tests**

Create `tests/test_exclusion_ledger.py`:

```python
"""Tests for bin/log_exclusion.py — ExclusionLedger (§3.6.8)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent.parent


def _load_log_exclusion_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "log_exclusion", _HERE / "bin" / "log_exclusion.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["log_exclusion"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


log_exclusion = _load_log_exclusion_module()

_KEY = b"test-secret-of-at-least-32-characters-x"
_FIELDS: dict[str, str] = {
    "variant_config_hash": "a" * 64,
    "snapshot_hash": "b" * 64,
    "run_id": "run-001",
    "incident_id": "incident-042",
    "gate_check": "snapshot_hash_match",
    "reason": "hash mismatch between pipeline outputs",
    "analytic_consequence": "run-001 excluded from variant analysis",
}


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "exclusion_ledger.jsonl"


@pytest.fixture
def ledger(log_path: Path) -> Any:
    return log_exclusion.ExclusionLedger(key=_KEY, log_path=log_path)


# ── Tracking ref: tests/test_exclusion_ledger.py::test_append ─────────────────

def test_append(ledger: Any, log_path: Path) -> None:
    entry = ledger.append(_FIELDS.copy())
    assert entry["prev_signature"] == log_exclusion.GENESIS
    assert len(entry["signature"]) == 64
    int(entry["signature"], 16)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    json.loads(lines[0])  # valid JSON


# ── Schema ─────────────────────────────────────────────────────────────────────

def test_schema(ledger: Any) -> None:
    entry = ledger.append(_FIELDS.copy())
    required = {
        "timestamp_utc", "commit_sha", "prev_signature",
        "variant_config_hash", "snapshot_hash", "run_id",
        "incident_id", "gate_check", "reason", "analytic_consequence",
        "signature",
    }
    assert required <= set(entry.keys())
    assert entry["timestamp_utc"].endswith("Z")
    assert len(entry["signature"]) == 64
    assert entry["incident_id"] == "incident-042"


# ── Chain integrity ────────────────────────────────────────────────────────────

def test_chain_links_across_two_entries(ledger: Any) -> None:
    e1 = ledger.append({**_FIELDS, "run_id": "run-001"})
    e2 = ledger.append({**_FIELDS, "run_id": "run-002"})
    assert e2["prev_signature"] == e1["signature"]


# ── Verify ─────────────────────────────────────────────────────────────────────

def test_verify_passes_on_clean_log(ledger: Any) -> None:
    ledger.append({**_FIELDS, "run_id": "run-001"})
    ledger.append({**_FIELDS, "run_id": "run-002"})
    ok, msg = ledger.verify()
    assert ok, msg


def test_verify_fails_on_tampered_log(ledger: Any, log_path: Path) -> None:
    ledger.append({**_FIELDS, "run_id": "run-001"})
    ledger.append({**_FIELDS, "run_id": "run-002"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["reason"] = "TAMPERED"
    lines[0] = json.dumps(entry, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, _ = ledger.verify()
    assert not ok


# ── Validation ─────────────────────────────────────────────────────────────────

def test_missing_required_field_raises(ledger: Any) -> None:
    with pytest.raises(ValueError, match="Missing required fields"):
        ledger.append({"variant_config_hash": "a" * 64})


def test_short_key_raises(log_path: Path) -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        log_exclusion.ExclusionLedger(key=b"short", log_path=log_path)


# ── load_key() ─────────────────────────────────────────────────────────────────

def test_missing_secret_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(log_exclusion.ENV_KEY, raising=False)
    with pytest.raises(SystemExit):
        log_exclusion.load_key()
```

- [ ] **Step 3.2: Run to confirm tests fail**

```bash
poetry run pytest tests/test_exclusion_ledger.py -v
```

Expected: tests fail — `ExclusionLedger` not defined in the stub.

- [ ] **Step 3.3: Implement `bin/log_exclusion.py`**

Replace the entire file:

```python
#!/usr/bin/env python3
"""Append a signed exclusion ledger entry to exclusion_ledger.jsonl.

Records runtime metric-integrity-gate failures (§3.6.8). Each entry is
HMAC-SHA256 chained identically to the deviation log. Written by the
metric integrity gate (Stage 1+) or this CLI for manual entries.

Schema (§3.6.8):
    timestamp_utc:        ISO-8601 with Z suffix (UTC)
    commit_sha:           Git commit SHA ($GITHUB_SHA in CI, else "LOCAL")
    prev_signature:       Hex signature of preceding entry, or "GENESIS"
    variant_config_hash:  64-char SHA-256 of the VCLManifest
    snapshot_hash:        64-char SHA-256 of the telemetry snapshot
    run_id:               Unique run identifier
    incident_id:          Corpus incident reference (links to result store)
    gate_check:           Which integrity check failed (e.g. snapshot_hash_match)
    reason:               Human-readable explanation
    analytic_consequence: Which runs / hypothesis is affected
    signature:            HMAC-SHA256 hex over canonical JSON of all above fields
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from helios.vcl.hmac_chain import GENESIS as GENESIS  # re-export for tests
from helios.vcl.hmac_chain import HMACChainedLog

HELIOS_ENABLE_EXCLUSION_LEDGER: bool = True  # always-on C1 audit infrastructure

LOG_FILE = Path("exclusion_ledger.jsonl")
ENV_KEY = "DEVIATION_HMAC_SECRET"


def load_key() -> bytes:
    """Read the HMAC secret from $DEVIATION_HMAC_SECRET. Exit on failure."""
    key = os.getenv(ENV_KEY)
    if not key:
        sys.stderr.write(
            f"ERROR: {ENV_KEY} not set. Copy .env.example to .env and set a secret.\n"
        )
        sys.exit(2)
    if len(key) < 32:
        sys.stderr.write(
            f"ERROR: {ENV_KEY} must be at least 32 characters (got {len(key)}).\n"
        )
        sys.exit(2)
    return key.encode("utf-8")


class ExclusionLedger(HMACChainedLog):
    """HMAC-chained log for metric-integrity-gate exclusion events (§3.6.8)."""

    REQUIRED_FIELDS = (
        "variant_config_hash",
        "snapshot_hash",
        "run_id",
        "incident_id",
        "gate_check",
        "reason",
        "analytic_consequence",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd")

    parser.add_argument("--variant-config-hash")
    parser.add_argument("--snapshot-hash")
    parser.add_argument("--run-id")
    parser.add_argument("--incident-id")
    parser.add_argument("--gate-check")
    parser.add_argument("--reason")
    parser.add_argument("--analytic-consequence")

    sub.add_parser("verify", help="Verify the entire HMAC chain.")

    args = parser.parse_args()

    if args.cmd == "verify":
        ledger = ExclusionLedger(key=load_key(), log_path=LOG_FILE)
        ok, msg = ledger.verify()
        print(("✅ " if ok else "❌ ") + msg)
        return 0 if ok else 1

    required_args = [
        "variant_config_hash", "snapshot_hash", "run_id",
        "incident_id", "gate_check", "reason", "analytic_consequence",
    ]
    missing = [r for r in required_args if not getattr(args, r, None)]
    if missing:
        flags = ", ".join("--" + m.replace("_", "-") for m in missing)
        parser.error(f"Missing required arguments: {flags}")

    fields = {
        "variant_config_hash": args.variant_config_hash,
        "snapshot_hash": args.snapshot_hash,
        "run_id": args.run_id,
        "incident_id": args.incident_id,
        "gate_check": args.gate_check,
        "reason": args.reason,
        "analytic_consequence": args.analytic_consequence,
    }
    ledger = ExclusionLedger(key=load_key(), log_path=LOG_FILE)
    entry = ledger.append(fields)
    print(
        f"✅ Exclusion logged: {entry['run_id']} | gate={entry['gate_check']}"
        f" | sig={entry['signature'][:12]}..."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3.4: Run tests — all must pass**

```bash
poetry run pytest tests/test_exclusion_ledger.py -v
```

Expected: 9 tests pass.

- [ ] **Step 3.5: Commit**

```bash
git add bin/log_exclusion.py tests/test_exclusion_ledger.py
git commit -m "feat(exclusion-ledger): implement ExclusionLedger with full test suite (S0-D2-ENG02)"
```

---

## Task 4: Documentation fixes

**Files:**
- Modify: `docs/tracking/HELIOS_MVP_Execution_plan_v0.6.md`
- Modify: `docs/tracking/helios_mvp_tracking.md`

- [ ] **Step 4.1: Fix execution plan filename reference**

In `docs/tracking/HELIOS_MVP_Execution_plan_v0.6.md`, find line 34:

```
3. Implement deviation log (`eval/deviation_log.py` — append-only JSONL + HMAC-SHA256).
```

Change to:

```
3. Implement deviation log (`bin/log_deviation.py` — append-only JSONL + HMAC-SHA256).
```

- [ ] **Step 4.2: Clarify filenames in tracking tasks**

In `docs/tracking/helios_mvp_tracking.md`, find the Notes column for S0-D2-ENG01 (currently `Ed25519 migration deferred`) and append a clarification. Find the Notes for S0-D2-ENG02 (currently `Required-field manifest`) and append. The Description column is immutable — only the Notes column is updated.

For S0-D2-ENG01 Notes, change from:
```
Ed25519 migration deferred
```
to:
```
Ed25519 migration deferred; implemented as bin/log_deviation.py
```

For S0-D2-ENG02 Notes, change from:
```
Required-field manifest
```
to:
```
Required-field manifest; implemented as bin/log_exclusion.py
```

- [ ] **Step 4.3: Update README stub comment**

In `README.md` line 34, change:

```
│   └── log_exclusion.py        # Stub (to be implemented Stage 1+)
```

to:

```
│   └── log_exclusion.py        # CLI: append signed entries to exclusion_ledger.jsonl (§3.6.8)
```

- [ ] **Step 4.4: Commit**

```bash
git add docs/tracking/HELIOS_MVP_Execution_plan_v0.6.md docs/tracking/helios_mvp_tracking.md README.md
git commit -m "docs: fix deviation_log filename references and update exclusion_ledger stub comment"
```

---

## Task 5: Full pre-push gate

Run the complete pre-push gate from `CLAUDE.md` in order. Fix any failures before proceeding.

- [ ] **Step 5.1: Lint**

```bash
poetry run ruff check helios/ scripts/ tests/ bin/
poetry run ruff format --check helios/ scripts/ tests/ bin/
```

Expected: no errors. If ruff flags issues, run `poetry run ruff check --fix ...` then `poetry run ruff format ...`.

- [ ] **Step 5.2: Type check**

```bash
poetry run mypy
```

Expected: no errors. Common issues to watch for:
- `Any` in function signatures needs `from typing import Any` in each file
- `dict[str, Any]` as return type — ensure annotations are complete
- `spec.loader.exec_module(mod)` in tests may need `# type: ignore[union-attr]` (loader is typed as `Optional[Loader]`)

- [ ] **Step 5.3: Full test suite with coverage**

```bash
poetry run pytest
```

Expected: all tests pass; coverage ≥ 90% on `helios/`. The new `helios/vcl/hmac_chain.py` must be fully covered by `tests/test_hmac_chain.py`.

- [ ] **Step 5.4: Deviation log chain verify**

```bash
set -a; source .env; set +a && poetry run python bin/log_deviation.py verify
```

Expected: `✅ Chain verified.`

- [ ] **Step 5.5: Tracking validation**

```bash
make validate-tracking
```

Expected: exit 0 (clean).

- [ ] **Step 5.6: Final commit if any auto-fixes were applied**

If ruff made any formatting changes in Step 5.1:

```bash
git add -u
git commit -m "style: apply ruff formatting to new modules"
```
