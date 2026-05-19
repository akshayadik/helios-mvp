# OSF Protocol Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and cryptographically sign six pre-registration artefacts under `research/osf/`, write the ablation notebook, and verify everything via a `--generate`/`--verify` CLI added to CI.

**Architecture:** Code-first — all six JSON artefacts are generated from Python constants and config files, never hand-written. `manifest_sig.txt` is SHA-256 over the six JSONs (alphabetical order). CI runs `--verify` on every push; mismatch or missing field = non-zero exit.

**Tech Stack:** Python 3.11, hashlib, tempfile, subprocess, PyYAML, pandas, jupyter nbconvert, `helios.vcl.utils.canonical_json`

---

## Pre-conditions (must pass before starting Task 1)

- Spec 1 merged: `gpipe_config.py` exists with `DISAGREEMENT_THRESHOLD` calibrated and frozen
- Spec 2 merged: `prompt_version_registry.md` has `rca_v1` YAML front-matter entry; `rca_v1.txt` committed
- `EXPECTED_PROMPT_SHA` in `lpipe_config.py` is a 64-char hex string (not `None`)
- `data/calibrated_params.json` has G-pipe LOO-CV fields: `gpipe_hr_at_3_held_out`, `dpipe_hr_at_3_held_out`, `gate_passed`, `n_incidents_triggered`
- `data/captures/*/manifest.json` all have `"schema_version": "schema-draft-v0.2"` and `"snapshot_hash"` populated
- Deviation log chain clean: `poetry run python bin/log_deviation.py verify` exits 0
- `poetry run pytest` green

---

## File Map

| File | Action |
|---|---|
| `helios/research/__init__.py` | Create — package marker |
| `helios/research/seeds.py` | Create — GLOBAL_SEED, LLAMA_SEED, SEED_REGISTRY |
| `helios/research/analysis_plan.py` | Create — FAMILY_A_HYPOTHESES, FAMILY_B_HYPOTHESES, helper functions |
| `research/__init__.py` | Create — package marker |
| `research/osf/` | Create directory |
| `bin/verify_osf_freeze.py` | Create — --generate, --verify, --populate-prereg |
| `research/osf/preregistration.md` | Create (human-authored) after --generate runs |
| `research/ablation_notebook.ipynb` | Create — L0–L3 sections |
| `.github/workflows/ci.yml` | Modify — add osf-freeze-verify + ablation-notebook jobs |
| `docs/tracking/tracking_documents_register.md` | Modify — add research/osf/ entries |
| `docs/tracking/reproducibility_manifest.md` | Modify — OSF freeze section |
| `docs/tracking/helios_mvp_tracking.md` | Modify — M3 Spec 3 DONE rows |
| `tests/research/__init__.py` | Create |
| `tests/research/test_seeds.py` | Create |
| `tests/research/test_analysis_plan.py` | Create |
| `tests/test_verify_osf_freeze.py` | Create |

---

## Task 1: helios/research package + seeds.py

**Files:**
- Create: `helios/research/__init__.py`
- Create: `helios/research/seeds.py`
- Create: `research/__init__.py`
- Create: `tests/research/__init__.py`
- Test: `tests/research/test_seeds.py`

- [ ] **Step 1: Write failing tests**

Create `tests/research/__init__.py` (empty file).

Create `tests/research/test_seeds.py`:

```python
"""Tests for helios.research.seeds — seed registry."""
from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_seed_registry_has_two_entries() -> None:
    from helios.research.seeds import SEED_REGISTRY
    assert len(SEED_REGISTRY) == 2


def test_seed_registry_global_seed_value() -> None:
    from helios.research.seeds import GLOBAL_SEED
    assert GLOBAL_SEED == 42


def test_seed_registry_llama_seed_value() -> None:
    from helios.research.seeds import LLAMA_SEED
    assert LLAMA_SEED == 42


def test_seed_registry_llama_seed_matches_lpipe_config() -> None:
    from helios.research.seeds import LLAMA_SEED as REG_SEED
    from helios.pipelines.l_pipe.lpipe_config import LLAMA_SEED as LPIPE_SEED
    assert REG_SEED == LPIPE_SEED


def test_seed_registry_entries_have_required_keys() -> None:
    from helios.research.seeds import SEED_REGISTRY
    required = {"seed_id", "value", "stage", "algorithm", "context", "source_constant"}
    for entry in SEED_REGISTRY:
        assert required <= entry.keys(), f"Missing keys in {entry}"


def test_seed_registry_seed_ids_are_unique() -> None:
    from helios.research.seeds import SEED_REGISTRY
    ids = [e["seed_id"] for e in SEED_REGISTRY]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/research/test_seeds.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'helios.research'`

- [ ] **Step 3: Create package files and seeds.py**

`helios/research/__init__.py` — empty file (package marker).

`research/__init__.py` — empty file (package marker).

`helios/research/seeds.py`:

```python
"""Research seed registry — single source of truth for all reproducibility seeds.

verify_osf_freeze.py --generate reads SEED_REGISTRY to produce seeds.json.
Any new seed requires a deviation log entry.
"""
from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

GLOBAL_SEED: int = 42
LLAMA_SEED: int = 42

SEED_REGISTRY: list[dict] = [
    {
        "seed_id": "SEED-001",
        "value": GLOBAL_SEED,
        "stage": "Stage 0",
        "algorithm": "global",
        "context": "numpy.random.seed / random.seed",
        "source_constant": "helios.research.seeds.GLOBAL_SEED",
    },
    {
        "seed_id": "SEED-002",
        "value": LLAMA_SEED,
        "stage": "Stage 1",
        "algorithm": "llama3.1:8b inference",
        "context": "Ollama Protocol A seed",
        "source_constant": "helios.pipelines.l_pipe.lpipe_config.LLAMA_SEED",
    },
]
```

Create `research/osf/` directory:

```bash
mkdir -p research/osf
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/research/test_seeds.py -v
```

Expected: 6 PASS

- [ ] **Step 5: Run full suite and lint**

```bash
poetry run pytest && poetry run ruff check helios/ tests/ && poetry run mypy
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add helios/research/__init__.py helios/research/seeds.py \
        research/__init__.py \
        tests/research/__init__.py tests/research/test_seeds.py
git commit -m "feat(osf): add helios/research package + seed registry"
```

---

## Task 2: analysis_plan.py

**Files:**
- Create: `helios/research/analysis_plan.py`
- Test: `tests/research/test_analysis_plan.py`

- [ ] **Step 1: Write failing tests**

`tests/research/test_analysis_plan.py`:

```python
"""Tests for helios.research.analysis_plan — frozen hypothesis tables."""
from __future__ import annotations

import pytest

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_family_a_hypotheses_has_eight_entries() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES
    assert len(FAMILY_A_HYPOTHESES) == 8


def test_family_b_hypotheses_has_eight_entries() -> None:
    from helios.research.analysis_plan import FAMILY_B_HYPOTHESES
    assert len(FAMILY_B_HYPOTHESES) == 8


def test_a_h3_is_rank_1_with_correct_alpha() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES
    a_h3 = next(h for h in FAMILY_A_HYPOTHESES if h["id"] == "A-H3")
    assert a_h3["rank"] == 1
    assert a_h3["alpha"] == pytest.approx(0.00625)


def test_a_h6_is_rank_5_with_filter_and_correct_alpha() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES
    a_h6 = next(h for h in FAMILY_A_HYPOTHESES if h["id"] == "A-H6")
    assert a_h6["rank"] == 5
    assert a_h6["alpha"] == pytest.approx(0.0125)
    assert a_h6["filter"] == "narrative != 'gpipe-gated-or-skipped'"


def test_non_a_h6_entries_have_null_filter() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES
    for h in FAMILY_A_HYPOTHESES:
        if h["id"] != "A-H6":
            assert h["filter"] is None, f"{h['id']} must have filter=None"


def test_family_a_ranks_are_unique_and_sequential() -> None:
    from helios.research.analysis_plan import FAMILY_A_HYPOTHESES
    ranks = sorted(h["rank"] for h in FAMILY_A_HYPOTHESES)
    assert ranks == list(range(1, 9))


def test_family_b_all_deferred() -> None:
    from helios.research.analysis_plan import FAMILY_B_HYPOTHESES
    for h in FAMILY_B_HYPOTHESES:
        assert h["status"] == "deferred"


def test_family_b_b_h2_and_b_h4_use_rcacopilot_baseline() -> None:
    from helios.research.analysis_plan import FAMILY_B_HYPOTHESES
    b_h2 = next(h for h in FAMILY_B_HYPOTHESES if h["id"] == "B-H2")
    b_h4 = next(h for h in FAMILY_B_HYPOTHESES if h["id"] == "B-H4")
    assert b_h2["baseline"] == "RCACopilot"
    assert b_h4["baseline"] == "RCACopilot"


def test_b_h7_primary_metric_is_coe_score() -> None:
    from helios.research.analysis_plan import FAMILY_B_HYPOTHESES
    b_h7 = next(h for h in FAMILY_B_HYPOTHESES if h["id"] == "B-H7")
    assert b_h7["primary_metric"] == "CoE score"


def test_hypothesis_for_variant_helios_full() -> None:
    from helios.research.analysis_plan import _hypothesis_for_variant
    result = _hypothesis_for_variant("HELIOS-Full")
    assert "A-H1" in result
    assert "A-H3" in result


def test_hypothesis_for_variant_helios_nollm() -> None:
    from helios.research.analysis_plan import _hypothesis_for_variant
    assert _hypothesis_for_variant("HELIOS-noLLM") == "A-H7"


def test_hypothesis_for_unknown_variant_returns_empty() -> None:
    from helios.research.analysis_plan import _hypothesis_for_variant
    assert _hypothesis_for_variant("HELIOS-Unknown") == ""


def test_status_for_variant_confirmatory() -> None:
    from helios.research.analysis_plan import _status_for_variant
    assert _status_for_variant("HELIOS-Full") == "confirmatory"
    assert _status_for_variant("HELIOS-D") == "confirmatory"


def test_status_for_variant_exploratory() -> None:
    from helios.research.analysis_plan import _status_for_variant
    assert _status_for_variant("HELIOS-noConsensus") == "exploratory"
    assert _status_for_variant("HELIOS-noRouter") == "exploratory"
    assert _status_for_variant("HELIOS-noStructural") == "exploratory"


def test_status_for_variant_conditional_confirmatory() -> None:
    from helios.research.analysis_plan import _status_for_variant
    assert _status_for_variant("HELIOS-G") == "cond. confirmatory"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/research/test_analysis_plan.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'helios.research.analysis_plan'`

- [ ] **Step 3: Write analysis_plan.py**

`helios/research/analysis_plan.py`:

```python
"""Frozen hypothesis tables — single source of truth for OSF pre-registration.

Changes require a deviation log entry.
FAMILY_A_HYPOTHESES and FAMILY_B_HYPOTHESES are consumed by
verify_osf_freeze.py --generate to produce analysis_plan.json.
"""
from __future__ import annotations

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

# Holm-Bonferroni ranks: rank 1 is most critical (strictest threshold).
# alpha(rank) = family_alpha / (n_hypotheses - rank + 1) = 0.05 / (9 - rank).
# Exact per-rank alphas: rank1=0.00625, rank2=0.007143, rank3=0.008333,
# rank4=0.01, rank5=0.0125, rank6=0.016667, rank7=0.025, rank8=0.05
FAMILY_A_HYPOTHESES: list[dict] = [
    {
        "id": "A-H3", "rank": 1,
        "comparison": "HELIOS-Full vs HELIOS-D",
        "primary_metric": "HR@3",
        "alpha": 0.00625,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H7", "rank": 2,
        "comparison": "HELIOS-Full vs HELIOS-noLLM",
        "primary_metric": "HR@3",
        "alpha": 0.007143,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H1", "rank": 3,
        "comparison": "HELIOS-Full vs baseline (fixed threshold)",
        "primary_metric": "HR@3",
        "alpha": 0.008333,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H2", "rank": 4,
        "comparison": "HELIOS-Full vs HELIOS-noGraph",
        "primary_metric": "CpR",
        "alpha": 0.01,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H6", "rank": 5,
        "comparison": "HELIOS-G vs HELIOS-D (gate-conditional)",
        "primary_metric": "HR@3",
        "alpha": 0.0125,
        "filter": "narrative != 'gpipe-gated-or-skipped'",
        "status": "confirmatory",
    },
    {
        "id": "A-H5", "rank": 6,
        "comparison": "HELIOS-Full vs HELIOS-noRouter",
        "primary_metric": "HR@3",
        "alpha": 0.016667,
        "filter": None,
        "status": "confirmatory",
    },
    {
        "id": "A-H4", "rank": 7,
        "comparison": "HELIOS-Full vs HELIOS-noConsensus",
        "primary_metric": "HR@3",
        "alpha": 0.025,
        "filter": None,
        "status": "exploratory",
    },
    {
        "id": "A-H8", "rank": 8,
        "comparison": "HELIOS-Full vs HELIOS-noStructural",
        "primary_metric": "HR@3",
        "alpha": 0.05,
        "filter": None,
        "status": "exploratory",
    },
]

# B-family: external baseline comparisons. Not derived from _VARIANT_HYPOTHESIS_MAP.
# B-H2 and B-H4 use RCACopilot as baseline; all others use CHASE.
# B-H7 primary_metric is "CoE score" (§2.2 Primary metric column, not "CoE quality").
FAMILY_B_HYPOTHESES: list[dict] = [
    {"id": "B-H1", "rank": 1, "comparison": "HELIOS-Full vs CHASE",      "primary_metric": "HR@3",               "status": "deferred", "baseline": "CHASE",      "note": "AIOpsLab corpus pending"},
    {"id": "B-H2", "rank": 2, "comparison": "HELIOS-Full vs RCACopilot", "primary_metric": "HR@3",               "status": "deferred", "baseline": "RCACopilot", "note": "AIOpsLab corpus pending"},
    {"id": "B-H3", "rank": 3, "comparison": "HELIOS-Full vs CHASE",      "primary_metric": "CpR",                "status": "deferred", "baseline": "CHASE",      "note": "AIOpsLab corpus pending"},
    {"id": "B-H4", "rank": 4, "comparison": "HELIOS-Full vs RCACopilot", "primary_metric": "CpR",                "status": "deferred", "baseline": "RCACopilot", "note": "AIOpsLab corpus pending"},
    {"id": "B-H5", "rank": 5, "comparison": "HELIOS-Full vs CHASE",      "primary_metric": "log-MTTR delta",     "status": "deferred", "baseline": "CHASE",      "note": "AIOpsLab corpus pending"},
    {"id": "B-H6", "rank": 6, "comparison": "HELIOS-Full vs CHASE",      "primary_metric": "hallucination rate", "status": "deferred", "baseline": "CHASE",      "note": "AIOpsLab corpus pending"},
    {"id": "B-H7", "rank": 7, "comparison": "HELIOS-Full vs CHASE",      "primary_metric": "CoE score",          "status": "deferred", "baseline": "CHASE",      "note": "AIOpsLab corpus pending"},
    {"id": "B-H8", "rank": 8, "comparison": "HELIOS-Full vs CHASE",      "primary_metric": "macro-F1",           "status": "deferred", "baseline": "CHASE",      "note": "AIOpsLab corpus pending"},
]

_VARIANT_HYPOTHESIS_MAP: dict[str, str] = {
    "HELIOS-Full":         "A-H1, A-H2, A-H3, A-H4, A-H5, A-H7, A-H8",
    "HELIOS-noLLM":        "A-H7",
    "HELIOS-noGraph":      "A-H2",
    "HELIOS-D":            "A-H3, A-H6",
    "HELIOS-G":            "A-H6",
    "HELIOS-noConsensus":  "A-H4",
    "HELIOS-noRouter":     "A-H5",
    "HELIOS-noStructural": "A-H8",
}

_VARIANT_STATUS_MAP: dict[str, str] = {
    "HELIOS-Full":         "confirmatory",
    "HELIOS-noLLM":        "confirmatory",
    "HELIOS-noGraph":      "confirmatory",
    "HELIOS-D":            "confirmatory",
    "HELIOS-G":            "cond. confirmatory",
    "HELIOS-noConsensus":  "exploratory",
    "HELIOS-noRouter":     "exploratory",
    "HELIOS-noStructural": "exploratory",
}


def _hypothesis_for_variant(name: str) -> str:
    return _VARIANT_HYPOTHESIS_MAP.get(name, "")


def _status_for_variant(name: str) -> str:
    return _VARIANT_STATUS_MAP.get(name, "exploratory")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/research/test_analysis_plan.py -v
```

Expected: 15 PASS

- [ ] **Step 5: Run full suite and lint**

```bash
poetry run pytest && poetry run ruff check helios/ tests/ && poetry run mypy
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add helios/research/analysis_plan.py tests/research/test_analysis_plan.py
git commit -m "feat(osf): add frozen hypothesis tables — FAMILY_A and FAMILY_B"
```

---

## Task 3: bin/verify_osf_freeze.py

**Files:**
- Create: `bin/verify_osf_freeze.py`
- Test: `tests/test_verify_osf_freeze.py`

- [ ] **Step 1: Write failing tests**

`tests/test_verify_osf_freeze.py`:

```python
"""Tests for verify_osf_freeze helper functions."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.utils import canonical_json


def _write_json(path: Path, data: dict) -> None:
    path.write_bytes((canonical_json(data) + "\n").encode("utf-8"))


def test_fault_class_parses_incident_id() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _fault_class
    assert _fault_class("s0-adhc-001") == "adhc"
    assert _fault_class("s0-cpuload-005") == "cpuload"
    assert _fault_class("nohyphen") == "unknown"


def test_verify_artefact_injects_timestamp_and_matches() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _verify_artefact

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "seeds.json"
        data = {
            "schema_version": "v1",
            "generated_at_iso": "2026-05-18T12:00:00+00:00",
            "seeds": [],
        }
        _write_json(path, data)
        # Different timestamp — verify must inject on-disk ts before comparing
        regen = {
            "schema_version": "v1",
            "generated_at_iso": "2099-01-01T00:00:00+00:00",
            "seeds": [],
        }
        assert _verify_artefact(path, regen) is True


def test_verify_artefact_detects_content_mismatch() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _verify_artefact

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "seeds.json"
        data = {
            "schema_version": "v1",
            "generated_at_iso": "2026-05-18T12:00:00+00:00",
            "seeds": [{"x": 1}],
        }
        _write_json(path, data)
        regen = {
            "schema_version": "v1",
            "generated_at_iso": "any",
            "seeds": [{"x": 2}],
        }
        assert _verify_artefact(path, regen) is False


def test_generate_manifest_sig_excludes_itself() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _generate_manifest_sig

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        a = tmp / "aaa.json"
        b = tmp / "bbb.json"
        a.write_bytes(b'{"x":1}\n')
        b.write_bytes(b'{"y":2}\n')
        _generate_manifest_sig(tmp)
        sig_path = tmp / "manifest_sig.txt"
        assert sig_path.exists()
        # manifest_sig.txt itself is excluded — only .json files concatenated
        expected = hashlib.sha256(b'{"x":1}\n' + b'{"y":2}\n').hexdigest()
        assert sig_path.read_text().strip() == expected


def test_preflight_fails_when_expected_sha_is_none(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _preflight_generate

    captures = tmp_path / "captures"
    captures.mkdir()
    params = tmp_path / "calibrated_params.json"
    params.write_bytes(
        b'{"gpipe_hr_at_3_held_out":0.6,"dpipe_hr_at_3_held_out":0.55,'
        b'"gate_passed":true,"n_incidents_triggered":8}'
    )

    with (
        patch("verify_osf_freeze.EXPECTED_PROMPT_SHA", None),
        patch("verify_osf_freeze.PROMPT_PATH", tmp_path / "no_prompt.txt"),
        patch("verify_osf_freeze._REGISTRY_PATH", tmp_path / "no_reg.md"),
        pytest.raises(SystemExit) as exc_info,
    ):
        _preflight_generate(captures, params)
    assert exc_info.value.code != 0


def test_preflight_fails_when_gpipe_fields_missing(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _preflight_generate

    captures = tmp_path / "captures"
    captures.mkdir()
    params = tmp_path / "calibrated_params.json"
    # Missing the G-pipe LOO-CV fields — only has D-pipe fields
    params.write_bytes(b'{"w_error":0.3,"rho_threshold":0.2}')

    with (
        patch("verify_osf_freeze.EXPECTED_PROMPT_SHA", "a" * 64),
        patch("verify_osf_freeze.PROMPT_PATH", tmp_path / "no_prompt.txt"),
        patch("verify_osf_freeze._REGISTRY_PATH", tmp_path / "no_reg.md"),
        pytest.raises(SystemExit),
    ):
        _preflight_generate(captures, params)


def test_vcl_freeze_sha_returns_nonempty_string() -> None:
    sys.path.insert(0, str(Path("bin")))
    from verify_osf_freeze import _vcl_freeze_sha
    result = _vcl_freeze_sha()
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_verify_osf_freeze.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'verify_osf_freeze'`

- [ ] **Step 3: Write bin/verify_osf_freeze.py**

```python
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
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


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


def _verify_artefact(path: Path, regenerated: dict) -> bool:
    on_disk_raw = path.read_bytes().replace(b"\r\n", b"\n")
    on_disk = json.loads(on_disk_raw)
    # Inject frozen timestamp so content comparison is clock-independent
    regenerated["generated_at_iso"] = on_disk["generated_at_iso"]
    regenerated_bytes = (canonical_json(regenerated) + "\n").encode("utf-8")
    return on_disk_raw == regenerated_bytes


def _generate_manifest_sig(osf_dir: Path) -> None:
    json_files = sorted(f for f in osf_dir.glob("*.json"))
    concatenated = b"".join(
        f.read_bytes().replace(b"\r\n", b"\n") for f in json_files
    )
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


# --- dict builders (shared by --generate and --verify) ---

def _build_seeds_dict() -> dict:
    return {"schema_version": "v1", "generated_at_iso": _now_iso(), "seeds": SEED_REGISTRY}


def _build_prompt_sha_dict() -> dict:
    front_matter = _REGISTRY_PATH.read_text(encoding="utf-8").split("---")[1]
    reg = yaml.safe_load(front_matter)
    entry = reg["entries"]["rca_v1"]
    return {
        "schema_version": "v1",
        "generated_at_iso": _now_iso(),
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": entry["sha256"],
        "model_name": MODEL_NAME,
        "model_family": "llama3.1",
        "frozen_at_milestone": "Milestone 3",
        "note": (
            "Production target: llama3.1:70b via vLLM. "
            "Deviation logged (see deviation_log entries 11-12)."
        ),
    }


def _build_thresholds_dict() -> dict:
    from helios.pipelines.d_pipe import dpipe_config
    from helios.pipelines.g_pipe import gpipe_config

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
            "ppr_alpha": dpipe_config.PPR_ALPHA,
            "pruner_efficacy_gate": dpipe_config.PRUNER_EFFICACY_GATE,
            "pruner_threshold": dpipe_config.PRUNER_THRESHOLD,
            "rho_threshold": params.get("rho_threshold"),
            "topology_boost_factor": params.get("topology_boost_factor"),
            "w_error": params.get("w_error"),
        },
        "gpipe": {
            "disagreement_threshold": gpipe_config.DISAGREEMENT_THRESHOLD,
            "ppr_alpha": dpipe_config.PPR_ALPHA,
            "frozen_at_milestone": "Milestone 3",
            "gpipe_hr_at_3_held_out": params["gpipe_hr_at_3_held_out"],
            "dpipe_hr_at_3_held_out": params["dpipe_hr_at_3_held_out"],
            "gate_passed": params["gate_passed"],
            "n_incidents_triggered": params["n_incidents_triggered"],
        },
    }


def _build_variant_hashes_dict() -> dict:
    vcl_sha = _vcl_freeze_sha()
    variants_out = []
    for name, manifest in CONFIRMATORY_VARIANTS.items():
        flags = {k: v for k, v in manifest.model_dump().items() if k in _VCL_FLAG_KEYS}
        variants_out.append({
            "name": name,
            "variant_config_hash": manifest.compute_variant_config_hash(),
            "hypothesis": _hypothesis_for_variant(name),
            "status": _status_for_variant(name),
            "flags": flags,
        })
    return {
        "schema_version": "v1",
        "generated_at_iso": _now_iso(),
        "vcl_freeze_sha": vcl_sha,
        "variants": variants_out,
    }


def _build_analysis_plan_dict() -> dict:
    data = {
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


def _build_corpus_manifest_dict() -> dict:
    incidents = []
    if CAPTURES_DIR.exists():
        for d in sorted(CAPTURES_DIR.iterdir()):
            if not d.is_dir():
                continue
            manifest_path = d / "manifest.json"
            if not manifest_path.exists():
                continue
            cap = json.loads(manifest_path.read_bytes())
            incidents.append({
                "incident_id": cap["incident_id"],
                "snapshot_hash": cap["snapshot_hash"],
                "fault_class": _fault_class(cap["incident_id"]),
            })
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


def _write_artefact(path: Path, data: dict) -> None:
    path.write_bytes((canonical_json(data) + "\n").encode("utf-8"))


# --- generate command ---

def _cmd_generate() -> None:
    _preflight_generate(CAPTURES_DIR, CALIBRATED_PARAMS_PATH)
    OSF_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OSF_DIR.parent) as _tmp:
        tmp_dir = Path(_tmp)
        _write_artefact(tmp_dir / "seeds.json",          _build_seeds_dict())
        _write_artefact(tmp_dir / "prompt_sha.json",     _build_prompt_sha_dict())
        _write_artefact(tmp_dir / "thresholds.json",     _build_thresholds_dict())
        _write_artefact(tmp_dir / "variant_hashes.json", _build_variant_hashes_dict())
        _write_artefact(tmp_dir / "analysis_plan.json",  _build_analysis_plan_dict())
        _write_artefact(tmp_dir / "corpus_manifest.json", _build_corpus_manifest_dict())
        _generate_manifest_sig(tmp_dir)  # must be last
        for fname in sorted(tmp_dir.glob("*")):
            shutil.move(str(fname), str(OSF_DIR / fname.name))
    print(f"--generate: 7 artefacts written to {OSF_DIR}")


# --- verify command ---

def _cmd_verify() -> None:
    errors: list[str] = []

    artefacts: list[tuple[str, dict]] = [
        ("seeds.json",          _build_seeds_dict()),
        ("prompt_sha.json",     _build_prompt_sha_dict()),
        ("thresholds.json",     _build_thresholds_dict()),
        ("variant_hashes.json", _build_variant_hashes_dict()),
        ("analysis_plan.json",  _build_analysis_plan_dict()),
        ("corpus_manifest.json", _build_corpus_manifest_dict()),
    ]
    for fname, regen in artefacts:
        path = OSF_DIR / fname
        if not path.exists():
            errors.append(f"Missing: {path}")
            continue
        if not _verify_artefact(path, regen):
            errors.append(f"Content mismatch: {fname}")

    # Verify A-H6 filter field is present in on-disk analysis_plan.json
    ap_path = OSF_DIR / "analysis_plan.json"
    if ap_path.exists():
        ap = json.loads(ap_path.read_bytes())
        a_h6_entries = [h for h in ap.get("family_a_hypotheses", []) if h["id"] == "A-H6"]
        if not a_h6_entries or not a_h6_entries[0].get("filter"):
            errors.append("A-H6 missing filter field in analysis_plan.json")
        if len(ap.get("family_b_hypotheses", [])) != 8:
            errors.append("analysis_plan.json: family_b_hypotheses must have 8 entries")

    # Verify manifest_sig
    json_files = sorted(f for f in OSF_DIR.glob("*.json"))
    concatenated = b"".join(f.read_bytes().replace(b"\r\n", b"\n") for f in json_files)
    expected_sig = hashlib.sha256(concatenated).hexdigest()
    sig_path = OSF_DIR / "manifest_sig.txt"
    if not sig_path.exists():
        errors.append("Missing: manifest_sig.txt")
    elif sig_path.read_text().strip() != expected_sig:
        errors.append("manifest_sig.txt mismatch")

    # Cross-check EXPECTED_PROMPT_SHA tamper-guard consistency
    prompt_sha_path = OSF_DIR / "prompt_sha.json"
    if prompt_sha_path.exists():
        frozen_sha = json.loads(prompt_sha_path.read_bytes())["prompt_sha256"]
        if EXPECTED_PROMPT_SHA is None:
            warnings.warn(
                "--verify: EXPECTED_PROMPT_SHA is None — tamper-guard not active; "
                "complete Spec 2 bootstrap before OSF deposit (G3-7)"
            )
        elif EXPECTED_PROMPT_SHA != frozen_sha:
            errors.append(
                "EXPECTED_PROMPT_SHA mismatch with prompt_sha.json prompt_sha256"
            )

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        sys.exit(1)
    print("--verify: all artefacts match. OSF freeze intact.")


# --- populate-prereg command ---

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_verify_osf_freeze.py -v
```

Expected: 7 PASS

- [ ] **Step 5: Run full suite and lint**

```bash
poetry run pytest && poetry run ruff check bin/ helios/ tests/ && poetry run mypy
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add bin/verify_osf_freeze.py tests/test_verify_osf_freeze.py
git commit -m "feat(osf): add verify_osf_freeze.py --generate/--verify/--populate-prereg"
```

---

## Task 4: Run --generate, create preregistration.md, run --populate-prereg

**Pre-condition:** All pre-conditions from the spec must pass — `_preflight_generate` enforces them at runtime.

- [ ] **Step 1: Verify pre-conditions**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py verify
poetry run pytest
```

Both must exit 0 before proceeding.

- [ ] **Step 2: Run --generate**

```bash
poetry run python bin/verify_osf_freeze.py --generate
```

Expected output: `--generate: 7 artefacts written to research/osf`

Check all artefacts:

```bash
ls -la research/osf/
```

Expected files: `analysis_plan.json`, `corpus_manifest.json`, `manifest_sig.txt`, `prompt_sha.json`, `seeds.json`, `thresholds.json`, `variant_hashes.json`

- [ ] **Step 3: Run --verify immediately after --generate**

```bash
poetry run python bin/verify_osf_freeze.py --verify
```

Expected: `--verify: all artefacts match. OSF freeze intact.`

- [ ] **Step 4: Create preregistration.md**

Create `research/osf/preregistration.md`. The `<!-- SHA:filename -->` markers will be replaced by `--populate-prereg` in Step 5 — do NOT hand-enter SHA values.

```markdown
# HELIOS OSF Pre-registration

**Title:** HELIOS: A Hybrid Multi-Pipeline Root Cause Analysis Framework for Microservices

**Author:** Akshay Adik (PhD candidate)

**Freeze date:** 2026-05-18

**Milestone:** Milestone 3 — Conditional G-pipe + L-pipe + OSF Full Freeze

---

## Overview

HELIOS is a Design Science Research (DSR) artefact addressing the RQ: How can a hybrid multi-pipeline system (statistical + graph + LLM) reduce MTTR and improve explainability/trust for microservice incidents? The framework orchestrates three peer pipelines (D-pipe: statistical anomaly detection; G-pipe: graph traversal; L-pipe: LLM explanation) controlled by Variant Control Layer (VCL) feature flags that enable ablation studies.

---

## Hypotheses

### A-Family (Ablation)

Ranked by Holm priority. All require `evaluation_phase = confirmatory` data from AIOpsLab.

| Rank | H_ID | Comparison | Primary Metric | Holm alpha | Status |
|---|---|---|---|---|---|
| 1 | A-H3 | HELIOS-Full vs HELIOS-D | HR@3 | 0.00625 | Confirmatory |
| 2 | A-H7 | HELIOS-Full vs HELIOS-noLLM | HR@3 | 0.007143 | Confirmatory |
| 3 | A-H1 | HELIOS-Full vs baseline | HR@3 | 0.008333 | Confirmatory |
| 4 | A-H2 | HELIOS-Full vs HELIOS-noGraph | CpR | 0.01 | Confirmatory |
| 5 | A-H6 | HELIOS-G vs HELIOS-D (gate-conditional) | HR@3 | 0.0125 | Cond. Confirmatory |
| 6 | A-H5 | HELIOS-Full vs HELIOS-noRouter | HR@3 | 0.016667 | Confirmatory |
| 7 | A-H4 | HELIOS-Full vs HELIOS-noConsensus | HR@3 | 0.025 | Exploratory (underpowered) |
| 8 | A-H8 | HELIOS-Full vs HELIOS-noStructural | HR@3 | 0.05 | Exploratory (underpowered) |

**A-H6 sentinel filter (mandatory):** When the PPR disagreement gate does not fire,
`run_gpipe()` emits a sentinel row (`narrative = 'gpipe-gated-or-skipped'`). These rows
must be excluded before computing the A-H6 metric. The filter is baked into `analysis_plan.json`.

### B-Family (Baseline comparisons)

All deferred to post-Milestone 4 (AIOpsLab confirmatory corpus pending).

| Rank | H_ID | Comparison | Primary Metric | Baseline |
|---|---|---|---|---|
| 1 | B-H1 | HELIOS-Full vs CHASE | HR@3 | CHASE |
| 2 | B-H2 | HELIOS-Full vs RCACopilot | HR@3 | RCACopilot |
| 3 | B-H3 | HELIOS-Full vs CHASE | CpR | CHASE |
| 4 | B-H4 | HELIOS-Full vs RCACopilot | CpR | RCACopilot |
| 5 | B-H5 | HELIOS-Full vs CHASE | log-MTTR delta | CHASE |
| 6 | B-H6 | HELIOS-Full vs CHASE | hallucination rate | CHASE |
| 7 | B-H7 | HELIOS-Full vs CHASE | CoE score | CHASE |
| 8 | B-H8 | HELIOS-Full vs CHASE | macro-F1 | CHASE |

---

## Variants

8 confirmatory VCL variants. Complete flag matrix stored in `variant_hashes.json`.

| Variant | Status | Hypotheses |
|---|---|---|
| HELIOS-Full | Confirmatory | A-H1, A-H2, A-H3, A-H4, A-H5, A-H7, A-H8 |
| HELIOS-noLLM | Confirmatory | A-H7 |
| HELIOS-noGraph | Confirmatory | A-H2 |
| HELIOS-D | Confirmatory | A-H3, A-H6 |
| HELIOS-G | Cond. Confirmatory | A-H6 |
| HELIOS-noConsensus | Exploratory (underpowered) | A-H4 |
| HELIOS-noRouter | Exploratory (underpowered) | A-H5 |
| HELIOS-noStructural | Exploratory (underpowered) | A-H8 |

---

## Statistical Analysis Plan

- **Test:** Wilcoxon signed-rank (one-sided)
- **Correction:** Holm-Bonferroni family-wise over 8 A-family tests
- **Family alpha:** 0.05
- **Effect size commitment:** Cohen h >= 0.276
- **Fixed reproducibility seeds:** GLOBAL_SEED: 42, LLAMA_SEED: 42 (see `seeds.json`)

---

## Corpus

**Exploratory calibration corpus:** 20 OTEL Demo incidents (local environment). Snapshot
hashes stored in `corpus_manifest.json`. Two-environment firewall enforced — exploratory
and confirmatory data are never mixed.

**Confirmatory corpus:** AIOpsLab, target 174 incidents. Deferred to post-Milestone 4.

---

## Frozen Artefacts

| File | SHA-256 |
|---|---|
| `analysis_plan.json` | <!-- SHA:analysis_plan.json --> |
| `corpus_manifest.json` | <!-- SHA:corpus_manifest.json --> |
| `prompt_sha.json` | <!-- SHA:prompt_sha.json --> |
| `seeds.json` | <!-- SHA:seeds.json --> |
| `thresholds.json` | <!-- SHA:thresholds.json --> |
| `variant_hashes.json` | <!-- SHA:variant_hashes.json --> |
| `manifest_sig.txt` | <!-- SHA:manifest_sig.txt --> |

---

## Deviation Summary

All protocol deviations with analytic consequence are logged in `deviation_log.jsonl`
(HMAC-SHA256 chained). List each entry by stage, clause, change, reason, and analytic
consequence. Entries 1-12 covering Milestones 1-3 must be listed before OSF deposit.

[Populate from deviation_log.jsonl before OSF deposit — no TBD sections permitted at G3-5 gate]

---

## OSF Deposit DOI

[to be added post-upload]
```

- [ ] **Step 5: Populate SHA markers**

```bash
poetry run python bin/verify_osf_freeze.py --populate-prereg
```

Expected output: `preregistration.md: 7 SHA markers populated`

Verify:

```bash
grep -c 'SHA:' research/osf/preregistration.md
```

Expected: 7 (each `<!-- SHA:filename -->` marker is now followed by a 64-char hex).

- [ ] **Step 6: Commit generated artefacts + preregistration.md**

```bash
git add research/osf/
git commit -m "feat(osf): generate protocol freeze artefacts + preregistration.md"
```

---

## Task 5: ablation_notebook.ipynb

**Files:**
- Create: `research/ablation_notebook.ipynb`

- [ ] **Step 1: Check nbformat is available**

```bash
poetry run python -c "import nbformat; print('ok')"
```

If this fails:

```bash
poetry add --group dev nbformat jupyter nbconvert
poetry lock
git add pyproject.toml poetry.lock
```

- [ ] **Step 2: Create the notebook via helper script**

Create `tmp_create_notebook.py` at repo root (delete after running):

```python
"""One-shot notebook creation helper — delete after running."""
import nbformat

SETUP = """\
import json
from pathlib import Path

OSF_DIR = Path("research/osf")

osf_seeds = json.loads((OSF_DIR / "seeds.json").read_bytes())
thresholds = json.loads((OSF_DIR / "thresholds.json").read_bytes())
variant_hashes = json.loads((OSF_DIR / "variant_hashes.json").read_bytes())
prompt_sha = json.loads((OSF_DIR / "prompt_sha.json").read_bytes())
analysis_plan = json.loads((OSF_DIR / "analysis_plan.json").read_bytes())

print(f"Generated at: {osf_seeds['generated_at_iso']}")
"""

FLAG_MATRIX = """\
import pandas as pd

rows = []
for v in variant_hashes["variants"]:
    row = {"variant": v["name"], "status": v["status"]}
    row.update(v["flags"])
    rows.append(row)

df = pd.DataFrame(rows).set_index("variant")
bool_cols = [c for c in df.columns if c not in ("status", "ingest_mode")]
df[bool_cols] = df[bool_cols].map(lambda x: "Y" if x else "N")
df
"""

DPIPE = """\
dpipe = thresholds["dpipe"]
print("D-pipe Calibration")
print(f"  Calibration incidents: {dpipe['calibration_incidents']}")
print(f"  PPR alpha: {dpipe['ppr_alpha']}")
print(f"  Pruner threshold: {dpipe['pruner_threshold']}")
print(f"  Rho threshold: {dpipe['rho_threshold']}")
print(f"  LOO-CV HR@3: {dpipe['loo_cv_hr_at_3']:.4f}")
print(f"  LOO-CV CpR: {dpipe['loo_cv_cpr']:.4f}")
"""

GPIPE = """\
gpipe = thresholds["gpipe"]
print("G-pipe Calibration")
print(f"  Disagreement threshold: {gpipe['disagreement_threshold']}")
print(f"  PPR alpha: {gpipe['ppr_alpha']}")
print(f"  G-pipe LOO-CV HR@3 (held-out): {gpipe['gpipe_hr_at_3_held_out']}")
print(f"  D-pipe LOO-CV HR@3 (held-out): {gpipe['dpipe_hr_at_3_held_out']}")
print(f"  Gate passed: {gpipe['gate_passed']}")
print(f"  Incidents triggered: {gpipe['n_incidents_triggered']}")
print()
a_h6 = next(h for h in analysis_plan["family_a_hypotheses"] if h["id"] == "A-H6")
print(f"A-H6 sentinel filter: {a_h6['filter']}")
"""

LPIPE = """\
print("L-pipe Prompt Governance (Protocol A — frozen; no live inference)")
print(f"  Prompt version: {prompt_sha['prompt_version']}")
print(f"  Model: {prompt_sha['model_name']}")
print(f"  Prompt SHA-256: {prompt_sha['prompt_sha256']}")
print(f"  Frozen at: {prompt_sha['frozen_at_milestone']}")
print(f"  Note: {prompt_sha['note']}")
"""

nb = nbformat.v4.new_notebook()
nb.cells = [
    nbformat.v4.new_markdown_cell(
        "# HELIOS Ablation Notebook\n\nL0-L3 pipeline matrix. All data from frozen OSF artefacts only."
    ),
    nbformat.v4.new_code_cell(SETUP),
    nbformat.v4.new_markdown_cell("## L0 — VCL Flag Matrix\n\n8 confirmatory variants x 14 flags."),
    nbformat.v4.new_code_cell(FLAG_MATRIX),
    nbformat.v4.new_markdown_cell("## L1 — D-pipe Calibration\n\nLOO-CV results from Milestone 2."),
    nbformat.v4.new_code_cell(DPIPE),
    nbformat.v4.new_markdown_cell(
        "## L2 — G-pipe\n\nPPR disagreement gate calibration. "
        "A-H6 requires sentinel row exclusion (`narrative != 'gpipe-gated-or-skipped'`)."
    ),
    nbformat.v4.new_code_cell(GPIPE),
    nbformat.v4.new_markdown_cell(
        "## L3 — L-pipe Prompt Governance\n\nProtocol A settings — no live inference in this notebook."
    ),
    nbformat.v4.new_code_cell(LPIPE),
]
with open("research/ablation_notebook.ipynb", "w") as f:
    nbformat.write(nb, f)
print("research/ablation_notebook.ipynb created")
```

Run it:

```bash
poetry run python tmp_create_notebook.py
rm tmp_create_notebook.py
```

- [ ] **Step 3: Execute notebook to verify it renders without Ollama**

```bash
poetry run jupyter nbconvert --to notebook --execute \
  --ExecutePreprocessor.timeout=120 \
  research/ablation_notebook.ipynb
```

Expected: exits 0. L3 cell reads config values from JSON — no inference required.

- [ ] **Step 4: Commit**

```bash
git add research/ablation_notebook.ipynb
git commit -m "feat(osf): add ablation notebook L0-L3"
```

---

## Task 6: CI integration

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add two new jobs to ci.yml**

After the existing `test` job, add (indented at the same level as `test:`):

```yaml
  osf-freeze-verify:
    runs-on: ubuntu-22.04
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: poetry install --no-interaction --with dev
      - name: Verify OSF freeze
        run: poetry run python bin/verify_osf_freeze.py --verify

  ablation-notebook:
    runs-on: ubuntu-22.04
    needs: osf-freeze-verify
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: poetry install --no-interaction --with dev
      - name: Execute ablation notebook
        run: |
          poetry run jupyter nbconvert --to notebook --execute \
            --ExecutePreprocessor.timeout=120 \
            research/ablation_notebook.ipynb
```

Note: `--verify` does NOT call `_preflight_generate`, so it does not require `DEVIATION_HMAC_SECRET`. No `.env` sourcing needed in the verify CI step.

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML valid"
```

- [ ] **Step 3: Run full test suite**

```bash
poetry run pytest
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add osf-freeze-verify and ablation-notebook jobs"
```

---

## Task 7: Tracking docs + pre-push gate

**Files:**
- Modify: `docs/tracking/tracking_documents_register.md`
- Modify: `docs/tracking/reproducibility_manifest.md`
- Modify: `docs/tracking/helios_mvp_tracking.md`

- [ ] **Step 1: Update tracking_documents_register.md**

Add a section for Milestone 3 OSF artefacts:

```markdown
| `research/osf/seeds.json` | Generated | Reproducibility seed registry | `bin/verify_osf_freeze.py --generate` | Milestone 3 |
| `research/osf/prompt_sha.json` | Generated | Prompt version + SHA-256 tamper anchor | `bin/verify_osf_freeze.py --generate` | Milestone 3 |
| `research/osf/thresholds.json` | Generated | D-pipe + G-pipe calibrated thresholds | `bin/verify_osf_freeze.py --generate` | Milestone 3 |
| `research/osf/variant_hashes.json` | Generated | 8 variant config hashes + flag matrix | `bin/verify_osf_freeze.py --generate` | Milestone 3 |
| `research/osf/analysis_plan.json` | Generated | A-family + B-family hypothesis tables | `bin/verify_osf_freeze.py --generate` | Milestone 3 |
| `research/osf/corpus_manifest.json` | Generated | Exploratory corpus 20-incident manifest | `bin/verify_osf_freeze.py --generate` | Milestone 3 |
| `research/osf/manifest_sig.txt` | Generated | SHA-256 over 6 JSON artefacts | `bin/verify_osf_freeze.py --generate` | Milestone 3 |
| `research/osf/preregistration.md` | Human-authored | Pre-registration document for OSF deposit | Manual; SHAs injected by `--populate-prereg` | Milestone 3 |
| `research/ablation_notebook.ipynb` | Generated | L0-L3 ablation pipeline matrix notebook | Manual creation; CI executes via nbconvert | Milestone 3 |
```

- [ ] **Step 2: Update reproducibility_manifest.md**

Read `research/osf/manifest_sig.txt` and paste it into:

```markdown
## Milestone 3 OSF Freeze (2026-05-18)

All six artefacts generated by `bin/verify_osf_freeze.py --generate` from code-first sources.
Integrity anchor: `manifest_sig.txt` = SHA-256 over concatenated artefacts (alphabetical order).

Manifest signature: [paste contents of research/osf/manifest_sig.txt here]

Verified by CI job `osf-freeze-verify` on every push.
```

- [ ] **Step 3: Update helios_mvp_tracking.md — IN_PROGRESS**

Two-commit pattern. First: set Spec 3 ENG/GATE rows to `IN_PROGRESS` with today's date and SHA from Task 1 commit.

```bash
git add docs/tracking/
git commit -m "tracking(m3-spec3): mark Spec 3 rows IN_PROGRESS"
```

- [ ] **Step 4: Run pre-push gate**

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ bin/ tests/ && \
  poetry run ruff format --check helios/ scripts/ bin/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

All must exit 0.

- [ ] **Step 5: Update helios_mvp_tracking.md — DONE**

Mark all Spec 3 ENG/GATE rows DONE with today's date and current HEAD SHA.

```bash
git add docs/tracking/helios_mvp_tracking.md
git commit -m "tracking(m3-spec3): mark Spec 3 rows DONE — OSF protocol freeze complete"
```

---

## Exit Gates

| Gate | Evidence |
|---|---|
| G3-1 | `poetry run python bin/verify_osf_freeze.py --verify` exits 0 |
| G3-2 | `manifest_sig.txt` matches SHA of concatenated artefacts |
| G3-3 | Zero hand-written JSONs under `research/osf/` — all generated by `--generate` |
| G3-4 | CI `osf-freeze-verify` job passes on PR |
| G3-5 | `preregistration.md` complete — Deviation Summary populated from `deviation_log.jsonl`; no TBD sections |
| G3-6 | `poetry run jupyter nbconvert --execute research/ablation_notebook.ipynb` exits 0 |
| G3-7 | `EXPECTED_PROMPT_SHA` non-None AND matches `prompt_sha.json["prompt_sha256"]` — `--verify` emits WARNING while None |
| G3-8 | `tracking_documents_register.md` and `reproducibility_manifest.md` updated |
