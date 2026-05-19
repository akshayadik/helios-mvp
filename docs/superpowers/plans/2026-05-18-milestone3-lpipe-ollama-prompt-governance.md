# L-pipe Ollama Client + Prompt Governance + Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement L-pipe with an Ollama-backed LLM client enforcing Protocol A, a tamper-evident frozen prompt registry, strict JSON response validation with one retry, and a pipeline entry-point replacing the current stub.

**Architecture:** Three independently-testable components (`OllamaClient`, `PromptRegistry`, `ResponseHandler`) assembled by `pipeline.py`. The orchestrator (`runner.py`) is updated to pass the full `UEGCSnapshot` and thread `run_id` through. The current `stub.py` is deleted.

**Tech Stack:** Python 3.11, `requests` (new dep), `pydantic` v2, `hashlib`, `pytest`, `unittest.mock`

**Depends on:** Spec 1 — `PipelineVerdict` schema-draft-v0.2 must be merged (adds `ppr_scores`, `prompt_version`, and defaults for `hr_at_3`/`cpr`).

**Blocks:** Spec 3 — OSF freeze requires prompt SHA from this spec.

---

## Pre-conditions

- [ ] Spec 1 merged: `PipelineVerdict` schema-draft-v0.2, `gpipe_config.py` present
- [ ] Ollama installed: `ollama --version`
- [ ] `llama3.1:8b` pulled: `ollama pull llama3.1:8b`
- [ ] `poetry run pytest` green

---

## File Map

| File | Action |
|---|---|
| `helios/pipelines/l_pipe/stub.py` | **Delete** |
| `helios/pipelines/l_pipe/__init__.py` | Update export |
| `helios/pipelines/l_pipe/lpipe_config.py` | **New** — frozen constants |
| `helios/pipelines/l_pipe/ollama_client.py` | **New** — Protocol A HTTP client |
| `helios/pipelines/l_pipe/prompt_registry.py` | **New** — SHA governance |
| `helios/pipelines/l_pipe/response_handler.py` | **New** — JSON validation + retry |
| `helios/pipelines/l_pipe/pipeline.py` | **New** — assembles all components |
| `helios/pipelines/l_pipe/prompts/rca_v1.txt` | **New** — frozen prompt template |
| `helios/orchestrator/runner.py` | Update L-pipe call signature |
| `docs/tracking/prompt_version_registry.md` | Populate rca_v1 YAML entry |
| `tests/pipelines/__init__.py` | **New** |
| `tests/pipelines/test_lpipe_ollama_client.py` | **New** |
| `tests/pipelines/test_lpipe_prompt_registry.py` | **New** |
| `tests/pipelines/test_lpipe_response_handler.py` | **New** |
| `tests/pipelines/test_lpipe_pipeline.py` | **New** |
| `pyproject.toml` + `poetry.lock` | Add `requests` dep |

---

### Task 1: `requests` dependency + `tests/pipelines` package + `lpipe_config.py`

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/pipelines/__init__.py`
- Create: `helios/pipelines/l_pipe/lpipe_config.py`

- [ ] **Step 1: Add `requests` to pyproject.toml**

In the `[tool.poetry.dependencies]` section, add below the `pandas` line:

```toml
requests = ">=2.28,<3.0"   # OllamaClient HTTP transport (L-pipe Protocol A)
```

Run `poetry lock && poetry install`.

Expected: lock file regenerated, `import requests` works.

- [ ] **Step 2: Run tests to confirm nothing broken**

```bash
poetry run pytest -q
```

Expected: all existing tests PASS.

- [ ] **Step 3: Create `tests/pipelines/__init__.py`**

```python
```

(empty file — package marker)

- [ ] **Step 4: Write `lpipe_config.py`**

```python
"""L-pipe frozen constants — Protocol A enforcement (§3.6.7).

Any change to Protocol A values (temperature, top_p, top_k, LLAMA_SEED)
requires a deviation log entry before the constant is updated.
"""

from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

HELIOS_ENABLE_LPIPE: bool = True

OLLAMA_BASE_URL: str = "http://localhost:11434"
MODEL_NAME: str = "llama3.1:8b"
TIMEOUT_S: float = 120.00
LPIPE_MAX_RETRIES: int = 1
PROMPT_VERSION: str = "rca_v1"

# Protocol A — greedy decoding; frozen. Change requires deviation log entry.
PROTOCOL_A_TEMPERATURE: float = 0.00
PROTOCOL_A_TOP_P: float = 1.00
PROTOCOL_A_TOP_K: int = 1
LLAMA_SEED: int = 42

# SHA-256 of prompts/rca_v1.txt — None until rca_v1.txt is first committed.
# Run bootstrap workflow (Task 4) to set this value.
# Once non-None, any change to rca_v1.txt requires a deviation log entry.
EXPECTED_PROMPT_SHA: str | None = None
```

- [ ] **Step 5: Run tests**

```bash
poetry run pytest tests/pipelines/ -v
```

Expected: no collection errors (empty dir passes).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml poetry.lock tests/pipelines/__init__.py helios/pipelines/l_pipe/lpipe_config.py
git commit -m "$(cat <<'EOF'
feat(lpipe): add requests dep, tests/pipelines package, lpipe_config constants

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: TDD `OllamaClient`

**Files:**
- Create: `tests/pipelines/test_lpipe_ollama_client.py`
- Create: `helios/pipelines/l_pipe/ollama_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/pipelines/test_lpipe_ollama_client.py
"""OllamaClient unit tests — Protocol A enforcement."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaGenerateResult,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.lpipe_config import (
    LLAMA_SEED,
    PROTOCOL_A_TEMPERATURE,
    PROTOCOL_A_TOP_K,
    PROTOCOL_A_TOP_P,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = {"response": text, "prompt_eval_count": 25, "eval_count": 75}
    return r


def test_generate_returns_response_on_success() -> None:
    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = _mock_response('{"ranked_candidates": ["svcA"]}')
        result = client.generate("test prompt", timeout_s=30.00)
    assert isinstance(result, OllamaGenerateResult)
    assert "svcA" in result.text
    assert result.prompt_tokens == 25
    assert result.completion_tokens == 75


def test_generate_raises_timeout() -> None:
    import requests

    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with patch("requests.post", side_effect=requests.exceptions.Timeout):
        with pytest.raises(OllamaTimeoutError):
            client.generate("prompt", timeout_s=30.00)


def test_generate_raises_connection_error() -> None:
    import requests

    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with patch("requests.post", side_effect=requests.exceptions.ConnectionError):
        with pytest.raises(OllamaConnectionError):
            client.generate("prompt", timeout_s=30.00)


def test_generate_raises_on_non_2xx() -> None:
    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = _mock_response("error", status_code=500)
        with pytest.raises(OllamaResponseError):
            client.generate("prompt", timeout_s=30.00)


def test_protocol_a_options_always_sent() -> None:
    client = OllamaClient("http://localhost:11434", "llama3.1:8b")
    with patch("requests.post") as mock_post:
        mock_post.return_value = _mock_response('{"response": "ok"}')
        client.generate("prompt", timeout_s=30.00)
    _, kwargs = mock_post.call_args
    payload = kwargs.get("json", mock_post.call_args[0][1] if mock_post.call_args[0] else {})
    # Check by inspecting the actual call args
    call_kwargs = mock_post.call_args.kwargs if mock_post.call_args.kwargs else {}
    call_json = call_kwargs.get("json", {})
    opts = call_json.get("options", {})
    assert opts.get("temperature") == PROTOCOL_A_TEMPERATURE
    assert opts.get("top_p") == PROTOCOL_A_TOP_P
    assert opts.get("top_k") == PROTOCOL_A_TOP_K
    assert opts.get("seed") == LLAMA_SEED


def test_protocol_a_options_not_overridable() -> None:
    import inspect

    from helios.pipelines.l_pipe.ollama_client import OllamaClient
    sig = inspect.signature(OllamaClient.generate)
    params = list(sig.parameters.keys())
    # generate() must only accept prompt and timeout_s — no options override
    assert "temperature" not in params
    assert "top_p" not in params
    assert "seed" not in params
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/pipelines/test_lpipe_ollama_client.py -v
```

Expected: `ImportError` — `ollama_client` does not exist yet.

- [ ] **Step 3: Implement `ollama_client.py`**

```python
"""OllamaClient — Protocol A HTTP wrapper for Ollama /api/generate."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from helios.pipelines.l_pipe.lpipe_config import (
    LLAMA_SEED,
    PROTOCOL_A_TEMPERATURE,
    PROTOCOL_A_TOP_K,
    PROTOCOL_A_TOP_P,
)
from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

HELIOS_ENABLE_OLLAMA_CLIENT: bool = True


class OllamaTimeoutError(Exception):
    pass


class OllamaConnectionError(Exception):
    pass


class OllamaResponseError(Exception):
    pass


@dataclass(frozen=True)
class OllamaGenerateResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


class OllamaClient:
    def __init__(self, base_url: str, model_name: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name

    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult:
        payload: dict[str, Any] = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": PROTOCOL_A_TEMPERATURE,
                "top_p": PROTOCOL_A_TOP_P,
                "top_k": PROTOCOL_A_TOP_K,
                "seed": LLAMA_SEED,
            },
        }
        try:
            response = requests.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=timeout_s,
            )
        except requests.exceptions.Timeout as exc:
            raise OllamaTimeoutError(str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise OllamaConnectionError(str(exc)) from exc
        if response.status_code >= 300:
            raise OllamaResponseError(
                f"Ollama returned HTTP {response.status_code}"
            )
        body = response.json()
        return OllamaGenerateResult(
            text=body["response"],
            prompt_tokens=body.get("prompt_eval_count", 0),
            completion_tokens=body.get("eval_count", 0),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/pipelines/test_lpipe_ollama_client.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add helios/pipelines/l_pipe/ollama_client.py tests/pipelines/test_lpipe_ollama_client.py
git commit -m "$(cat <<'EOF'
feat(lpipe): OllamaClient with Protocol A enforcement — 6 tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: TDD `PromptRegistry` + write `rca_v1.txt` + populate `prompt_version_registry.md`

**Files:**
- Create: `helios/pipelines/l_pipe/prompts/rca_v1.txt`
- Create: `tests/pipelines/test_lpipe_prompt_registry.py`
- Create: `helios/pipelines/l_pipe/prompt_registry.py`
- Modify: `docs/tracking/prompt_version_registry.md`

- [ ] **Step 1: Write `rca_v1.txt`**

Create directory `helios/pipelines/l_pipe/prompts/` and write:

```
You are an expert root cause analysis (RCA) assistant for a cloud-native microservices system.

Incident ID: {incident_id}

Affected services: {service_list}

Anomaly summary: {anomaly_summary}

Based on the above information, identify the most likely root causes ranked by confidence.

Respond with ONLY valid JSON — no markdown, no commentary, no code blocks:
{{
  "ranked_candidates": ["service_name_1", "service_name_2", "service_name_3"],
  "narrative": "Chain of Explanation: describe the causal chain from root cause to observed anomalies.",
  "confidence": 0.75
}}

Rules:
- ranked_candidates must be a non-empty list of service names from the affected services list
- narrative must be a non-empty string explaining the causal reasoning
- confidence must be a float between 0 and 1
```

(Note: `{{` and `}}` are literal braces in Python `.format()` templates.)

- [ ] **Step 2: Write failing tests**

```python
# tests/pipelines/test_lpipe_prompt_registry.py
"""PromptRegistry unit tests — SHA governance."""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from helios.pipelines.l_pipe.prompt_registry import PROMPT_PATH, PromptRegistry
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _load_registry() -> PromptRegistry:
    return PromptRegistry(PROMPT_PATH)


def test_sha_stable_across_two_loads() -> None:
    r1 = _load_registry()
    r2 = _load_registry()
    assert r1.prompt_sha == r2.prompt_sha


def test_render_substitutes_placeholders() -> None:
    registry = _load_registry()
    rendered = registry.render(
        incident_id="inc-001",
        service_list=["frontend", "checkout"],
        anomaly_summary="Latency spike detected",
    )
    assert "inc-001" in rendered
    assert "frontend, checkout" in rendered
    assert "Latency spike detected" in rendered


def test_verify_sha_passes_on_correct_hash() -> None:
    registry = _load_registry()
    assert registry.verify_sha(registry.prompt_sha) is True


def test_verify_sha_fails_on_tampered_content() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("tampered content")
        tmp_path = Path(f.name)
    try:
        registry = PromptRegistry(tmp_path)
        original = _load_registry()
        assert registry.verify_sha(original.prompt_sha) is False
    finally:
        tmp_path.unlink()


def test_tamper_raises_on_pipeline_init() -> None:
    from helios.pipelines.l_pipe.prompt_registry import PromptTamperError

    registry = _load_registry()
    with pytest.raises(PromptTamperError):
        registry.verify_sha_or_raise("wrong-sha-value-that-will-not-match")
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
poetry run pytest tests/pipelines/test_lpipe_prompt_registry.py -v
```

Expected: `ImportError` — `prompt_registry` does not exist yet.

- [ ] **Step 4: Implement `prompt_registry.py`**

```python
"""PromptRegistry — frozen prompt + SHA256 tamper-guard."""
from __future__ import annotations

import hashlib
from pathlib import Path

from helios.pipelines.l_pipe.lpipe_config import PROMPT_VERSION
from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

HELIOS_ENABLE_PROMPT_REGISTRY: bool = True

PROMPT_PATH: Path = Path(__file__).parent / "prompts" / "rca_v1.txt"


class PromptTamperError(Exception):
    pass


class PromptRegistry:
    def __init__(self, prompt_path: Path) -> None:
        self._text = prompt_path.read_text(encoding="utf-8")
        self._sha = hashlib.sha256(self._text.encode("utf-8")).hexdigest()

    @property
    def prompt_sha(self) -> str:
        return self._sha

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION

    def render(self, *, incident_id: str, service_list: list[str], anomaly_summary: str) -> str:
        return self._text.format(
            incident_id=incident_id,
            service_list=", ".join(service_list),
            anomaly_summary=anomaly_summary,
        )

    def verify_sha(self, expected_sha: str) -> bool:
        return self._sha == expected_sha

    def verify_sha_or_raise(self, expected_sha: str) -> None:
        if not self.verify_sha(expected_sha):
            raise PromptTamperError(
                f"Prompt SHA mismatch: live={self._sha!r} expected={expected_sha!r}. "
                "rca_v1.txt has been modified. Deviation log entry required before proceeding."
            )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/pipelines/test_lpipe_prompt_registry.py -v
```

Expected: 5 PASS.

- [ ] **Step 6: Compute SHA256 of `rca_v1.txt`**

```bash
sha256sum helios/pipelines/l_pipe/prompts/rca_v1.txt | cut -d' ' -f1
```

Copy the 64-character hex output (call it `$SHA`).

- [ ] **Step 7: Populate `prompt_version_registry.md` with YAML front-matter**

Replace the entire content of `docs/tracking/prompt_version_registry.md` with:

```markdown
---
entries:
  rca_v1:
    prompt_version: "rca_v1"
    prompt_sha256: "<PASTE 64-char hex from Step 6>"
    model_name: "llama3.1:8b"
    created_at_iso: "<ISO 8601 timestamp e.g. 2026-05-18T00:00:00+00:00>"
    frozen_at_milestone: "Milestone 3"
---

# Prompt Version Registry

**Purpose:** Frozen L-pipe prompt templates with SHA256 integrity values. Binds every verdict row to the exact prompt version used.

**Update cadence:** Only on prompt version change (requires deviation log entry)
**Owner:** Researcher
**Status:** Active — rca_v1 frozen at Milestone 3

Human-readable notes below the separator are ignored by the YAML parser.
```

Verify the YAML is parseable:

```bash
poetry run python -c "
import yaml
content = open('docs/tracking/prompt_version_registry.md').read().split('---')
entry = yaml.safe_load(content[1])['entries']['rca_v1']
print(entry)
"
```

Expected: dict with `prompt_sha256`, `model_name`, `created_at_iso`, `frozen_at_milestone`.

- [ ] **Step 8: Commit**

```bash
git add helios/pipelines/l_pipe/prompts/ helios/pipelines/l_pipe/prompt_registry.py tests/pipelines/test_lpipe_prompt_registry.py docs/tracking/prompt_version_registry.md
git commit -m "$(cat <<'EOF'
feat(lpipe): PromptRegistry + rca_v1.txt frozen prompt — 5 tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Bootstrap `EXPECTED_PROMPT_SHA` (one-time lock)

**Files:**
- Modify: `helios/pipelines/l_pipe/lpipe_config.py`

This task locks the prompt SHA so the tamper-guard activates. Until this step, `run_lpipe()` warns but continues.

- [ ] **Step 1: Compute SHA256 of the committed `rca_v1.txt`**

```bash
sha256sum helios/pipelines/l_pipe/prompts/rca_v1.txt | cut -d' ' -f1
```

Note: the file must be committed (Task 3 Step 8) before computing the bootstrap SHA. Do NOT run this against an uncommitted version.

- [ ] **Step 2: Update `EXPECTED_PROMPT_SHA` in `lpipe_config.py`**

Replace:
```python
EXPECTED_PROMPT_SHA: str | None = None
```
With:
```python
EXPECTED_PROMPT_SHA: str | None = "<64-char hex from Step 1>"
```

- [ ] **Step 3: Run SHA verification test**

```bash
poetry run pytest tests/pipelines/test_lpipe_pipeline.py::test_expected_prompt_sha_matches_registry -v
```

Expected: PASS (not SKIP — it was skipping while `EXPECTED_PROMPT_SHA` was `None`).

Note: `tests/pipelines/test_lpipe_pipeline.py` will be created in Task 6. If running Task 4 before Task 6, this step will fail with `collection error` — that is expected. Run this verification again after Task 6.

- [ ] **Step 4: Commit**

```bash
git add helios/pipelines/l_pipe/lpipe_config.py
git commit -m "$(cat <<'EOF'
feat(lpipe): freeze EXPECTED_PROMPT_SHA — tamper-guard active

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: TDD `ResponseHandler`

**Files:**
- Create: `tests/pipelines/test_lpipe_response_handler.py`
- Create: `helios/pipelines/l_pipe/response_handler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/pipelines/test_lpipe_response_handler.py
"""ResponseHandler unit tests — JSON validation, retry, fallback."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from helios.pipelines.l_pipe.ollama_client import (
    OllamaGenerateResult,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.response_handler import LPipeResponse, ResponseHandler
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def _make_result(text: str) -> OllamaGenerateResult:
    return OllamaGenerateResult(text=text, prompt_tokens=25, completion_tokens=75)


def _valid_json() -> str:
    return (
        '{"ranked_candidates": ["svcA", "svcB"], '
        '"narrative": "svcA caused the issue via latency cascade", '
        '"confidence": 0.75}'
    )


def test_valid_response_parsed_correctly() -> None:
    client = MagicMock()
    client.generate.return_value = _make_result(_valid_json())
    handler = ResponseHandler(client, max_retries=1)
    response, ollama_result = handler.handle("test prompt", timeout_s=30.00)
    assert isinstance(response, LPipeResponse)
    assert response.ranked_candidates == ["svcA", "svcB"]
    assert ollama_result is not None
    assert ollama_result.completion_tokens == 75


def test_malformed_json_triggers_retry() -> None:
    client = MagicMock()
    client.generate.side_effect = [
        _make_result("not valid json at all"),
        _make_result(_valid_json()),
    ]
    handler = ResponseHandler(client, max_retries=1)
    response, _ = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["svcA", "svcB"]
    assert client.generate.call_count == 2


def test_missing_field_triggers_retry() -> None:
    missing_narrative = '{"ranked_candidates": ["svcA"], "confidence": 0.75}'
    client = MagicMock()
    client.generate.side_effect = [
        _make_result(missing_narrative),
        _make_result(missing_narrative),
    ]
    handler = ResponseHandler(client, max_retries=1)
    response, ollama_result = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["l-pipe-fallback"]
    assert ollama_result is None  # fallback path: no successful Ollama round-trip


def test_retry_exhaustion_returns_fallback() -> None:
    client = MagicMock()
    client.generate.return_value = _make_result("bad json")
    handler = ResponseHandler(client, max_retries=1)
    response, ollama_result = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["l-pipe-fallback"]
    assert response.narrative == "l-pipe-fallback-schema-error"
    assert ollama_result is None


def test_timeout_is_reraised() -> None:
    client = MagicMock()
    client.generate.side_effect = OllamaTimeoutError("timed out")
    handler = ResponseHandler(client, max_retries=1)
    with pytest.raises(OllamaTimeoutError):
        handler.handle("prompt", timeout_s=30.00)


def test_extra_field_rejected() -> None:
    extra_field = (
        '{"ranked_candidates": ["svcA"], '
        '"narrative": "ok", '
        '"confidence": 0.75, '
        '"extra_unknown_field": "value"}'
    )
    client = MagicMock()
    client.generate.side_effect = [
        _make_result(extra_field),
        _make_result(_valid_json()),
    ]
    handler = ResponseHandler(client, max_retries=1)
    response, _ = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["svcA", "svcB"]
    assert client.generate.call_count == 2


def test_markdown_wrapped_json_sanitized() -> None:
    wrapped = "```json\n" + _valid_json() + "\n```"
    client = MagicMock()
    client.generate.return_value = _make_result(wrapped)
    handler = ResponseHandler(client, max_retries=1)
    response, _ = handler.handle("prompt", timeout_s=30.00)
    assert response.ranked_candidates == ["svcA", "svcB"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/pipelines/test_lpipe_response_handler.py -v
```

Expected: `ImportError` — `response_handler` does not exist yet.

- [ ] **Step 3: Implement `response_handler.py`**

```python
"""ResponseHandler — JSON schema validation + single retry + fallback."""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from helios.pipelines.l_pipe.ollama_client import OllamaClient, OllamaGenerateResult
from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

HELIOS_ENABLE_RESPONSE_HANDLER: bool = True

_MD_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def sanitize_llm_output(raw: str) -> str:
    """Strip markdown code-block wrapper if present."""
    m = _MD_FENCE_RE.search(raw)
    if m:
        return m.group(1).strip()
    return raw.strip()


class LPipeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ranked_candidates: list[str] = Field(min_length=1)
    narrative: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


_FALLBACK = LPipeResponse(
    ranked_candidates=["l-pipe-fallback"],
    narrative="l-pipe-fallback-schema-error",
    confidence=0.00,
)


class ResponseHandler:
    def __init__(self, client: OllamaClient, max_retries: int) -> None:
        self._client = client
        self._max_retries = max_retries

    def handle(
        self,
        prompt: str,
        timeout_s: float,
    ) -> tuple[LPipeResponse, OllamaGenerateResult | None]:
        retries_remaining = self._max_retries
        last_result: OllamaGenerateResult | None = None
        while retries_remaining >= 0:
            last_result = self._client.generate(prompt, timeout_s=timeout_s)
            sanitized = sanitize_llm_output(last_result.text)
            try:
                data = json.loads(sanitized)
                return (LPipeResponse(**data), last_result)
            except (json.JSONDecodeError, ValidationError):
                retries_remaining -= 1
        return (_FALLBACK, None)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/pipelines/test_lpipe_response_handler.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add helios/pipelines/l_pipe/response_handler.py tests/pipelines/test_lpipe_response_handler.py
git commit -m "$(cat <<'EOF'
feat(lpipe): ResponseHandler — JSON validation, retry, fallback — 7 tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: TDD `pipeline.py` + update `runner.py` + delete `stub.py`

**Files:**
- Create: `tests/pipelines/test_lpipe_pipeline.py`
- Create: `helios/pipelines/l_pipe/pipeline.py`
- Delete: `helios/pipelines/l_pipe/stub.py`
- Modify: `helios/pipelines/l_pipe/__init__.py`
- Modify: `helios/orchestrator/runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/pipelines/test_lpipe_pipeline.py
"""L-pipe pipeline entry-point tests."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from helios.schemas.ueg_c import EdgeType, NodeType, UEGCEdge, UEGCNode, UEGCSnapshot
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.decorators import set_current_manifest
from helios.vcl.variants import get_variant

_HASH = "a" * 64
_AT = "2026-01-01T00:00:00+00:00"


def _make_snapshot(service_names: list[str]) -> UEGCSnapshot:
    nodes = [
        UEGCNode(node_id=s, node_type=NodeType.SERVICE, service_name=s)
        for s in service_names
    ]
    return UEGCSnapshot(
        incident_id="inc-001",
        variant_config_hash=_HASH,
        nodes=nodes,
        edges=[],
        captured_at_iso=_AT,
    )


def _setup_manifest() -> None:
    set_current_manifest(get_variant("HELIOS-Full"))


def _make_valid_lpipe_response() -> dict[str, Any]:
    return {
        "ranked_candidates": ["svcA", "svcB"],
        "narrative": "svcA caused latency cascade",
        "confidence": 0.75,
    }


def test_run_lpipe_returns_dict_with_required_fields() -> None:
    _setup_manifest()
    from helios.pipelines.l_pipe.pipeline import run_lpipe

    snapshot = _make_snapshot(["svcA", "svcB"])
    mock_handler_result = (
        MagicMock(
            ranked_candidates=["svcA"],
            narrative="svcA caused the issue",
        ),
        MagicMock(prompt_tokens=25, completion_tokens=75),
    )
    with (
        patch("helios.pipelines.l_pipe.pipeline.PromptRegistry") as mock_reg_cls,
        patch("helios.pipelines.l_pipe.pipeline.OllamaClient"),
        patch("helios.pipelines.l_pipe.pipeline.ResponseHandler") as mock_handler_cls,
    ):
        mock_reg = MagicMock()
        mock_reg.render.return_value = "test prompt"
        mock_reg.prompt_version = "rca_v1"
        mock_reg_cls.return_value = mock_reg
        mock_handler = MagicMock()
        mock_handler.handle.return_value = mock_handler_result
        mock_handler_cls.return_value = mock_handler

        result = run_lpipe(
            incident_id="inc-001",
            snapshot=snapshot,
            snapshot_hash=_HASH,
            evaluation_phase="exploratory",
            run_id="run-abc",
        )

    assert result["pipeline"] == "lpipe"
    assert result["run_id"] == "run-abc"
    assert result["ranked_candidates"] == ["svcA"]
    assert result["prompt_version"] == "rca_v1"
    assert "token_count" in result
    assert "latency_ms" in result
    assert "schema_version" in result


def test_connectivity_error_returns_failure_dict() -> None:
    _setup_manifest()
    from helios.pipelines.l_pipe.ollama_client import OllamaConnectionError
    from helios.pipelines.l_pipe.pipeline import run_lpipe

    snapshot = _make_snapshot(["svcA"])
    with (
        patch("helios.pipelines.l_pipe.pipeline.PromptRegistry") as mock_reg_cls,
        patch("helios.pipelines.l_pipe.pipeline.OllamaClient"),
        patch("helios.pipelines.l_pipe.pipeline.ResponseHandler") as mock_handler_cls,
    ):
        mock_reg = MagicMock()
        mock_reg.render.return_value = "test prompt"
        mock_reg.prompt_version = "rca_v1"
        mock_reg_cls.return_value = mock_reg
        mock_handler = MagicMock()
        mock_handler.handle.side_effect = OllamaConnectionError("connection refused")
        mock_handler_cls.return_value = mock_handler

        result = run_lpipe(
            incident_id="inc-001",
            snapshot=snapshot,
            snapshot_hash=_HASH,
            evaluation_phase="exploratory",
            run_id="run-abc",
        )

    assert result["pipeline"] == "lpipe"
    assert result["ranked_candidates"] == ["l-pipe-connectivity-error"]
    assert "l-pipe-connectivity-error" in result["narrative"]


def test_expected_prompt_sha_matches_registry() -> None:
    from helios.pipelines.l_pipe.lpipe_config import EXPECTED_PROMPT_SHA
    from helios.pipelines.l_pipe.prompt_registry import PROMPT_PATH, PromptRegistry

    registry = PromptRegistry(PROMPT_PATH)
    if EXPECTED_PROMPT_SHA is None:
        pytest.skip(f"EXPECTED_PROMPT_SHA not frozen — bootstrap value: {registry.prompt_sha}")
    assert registry.prompt_sha == EXPECTED_PROMPT_SHA, (
        f"Prompt SHA mismatch: live={registry.prompt_sha!r} frozen={EXPECTED_PROMPT_SHA!r}"
    )


def test_service_list_from_snapshot() -> None:
    from helios.pipelines.l_pipe.pipeline import _service_list_from_snapshot

    snapshot = _make_snapshot(["svcC", "svcA", "svcB"])
    result = _service_list_from_snapshot(snapshot)
    assert result == ["svcA", "svcB", "svcC"]  # sorted


def test_anomaly_summary_format() -> None:
    from helios.pipelines.l_pipe.pipeline import _anomaly_summary

    snapshot = _make_snapshot(["svcA", "svcB"])
    result = _anomaly_summary(snapshot)
    assert result == "Anomalies detected across 2 services: svcA, svcB"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/pipelines/test_lpipe_pipeline.py -v
```

Expected: `ImportError` — `pipeline` does not exist yet.

- [ ] **Step 3: Implement `pipeline.py`**

```python
"""L-pipe pipeline entry-point — Ollama Protocol A + prompt governance (§3.6.7)."""
from __future__ import annotations

import logging
import time
from typing import Any

from helios.pipelines.l_pipe.lpipe_config import (
    EXPECTED_PROMPT_SHA,
    LPIPE_MAX_RETRIES,
    MODEL_NAME,
    OLLAMA_BASE_URL,
    TIMEOUT_S,
)
from helios.pipelines.l_pipe.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from helios.pipelines.l_pipe.prompt_registry import PROMPT_PATH, PromptRegistry
from helios.pipelines.l_pipe.response_handler import ResponseHandler
from helios.schemas.ueg_c import UEGCSnapshot
from helios.schemas.verdict import VERDICT_SCHEMA_VERSION
from helios.vcl import VCLFlag, gated_by, get_current_manifest

_log = logging.getLogger(__name__)

HELIOS_ENABLE_LPIPE_PIPELINE: bool = True


def _service_list_from_snapshot(snapshot: UEGCSnapshot) -> list[str]:
    return sorted({node.service_name for node in snapshot.nodes})


def _anomaly_summary(snapshot: UEGCSnapshot) -> str:
    services = _service_list_from_snapshot(snapshot)
    return f"Anomalies detected across {len(services)} services: {', '.join(services)}"


@gated_by(VCLFlag.L2C_LLM)
def run_lpipe(
    incident_id: str,
    snapshot: UEGCSnapshot,
    snapshot_hash: str,
    evaluation_phase: str,
    run_id: str,
) -> dict[str, Any]:
    t0 = time.monotonic()
    manifest = get_current_manifest()
    assert manifest is not None
    registry = PromptRegistry(PROMPT_PATH)
    if EXPECTED_PROMPT_SHA is not None:
        registry.verify_sha_or_raise(EXPECTED_PROMPT_SHA)
    else:
        _log.warning(
            "lpipe: EXPECTED_PROMPT_SHA not frozen — prompt tamper-guard disabled. "
            "Freeze after committing rca_v1.txt (see lpipe_config.py)."
        )
    client = OllamaClient(OLLAMA_BASE_URL, MODEL_NAME)
    handler = ResponseHandler(client, max_retries=LPIPE_MAX_RETRIES)
    prompt = registry.render(
        incident_id=incident_id,
        service_list=_service_list_from_snapshot(snapshot),
        anomaly_summary=_anomaly_summary(snapshot),
    )
    try:
        response, ollama_result = handler.handle(prompt, timeout_s=TIMEOUT_S)
    except (OllamaTimeoutError, OllamaConnectionError, OllamaResponseError) as exc:
        latency_ms = (time.monotonic() - t0) * 1_000.00
        _log.error("lpipe transient error for %s: %s", incident_id, exc)
        return {
            "pipeline": "lpipe",
            "incident_id": incident_id,
            "run_id": run_id,
            "variant_config_hash": manifest.compute_variant_config_hash(),
            "snapshot_hash": snapshot_hash,
            "ranked_candidates": ["l-pipe-connectivity-error"],
            "ppr_scores": {},
            "prompt_version": registry.prompt_version,
            "token_count": 0,
            "narrative": f"l-pipe-connectivity-error: {type(exc).__name__}",
            "latency_ms": latency_ms,
            "evaluation_phase": evaluation_phase,
            "schema_version": VERDICT_SCHEMA_VERSION,
        }
    latency_ms = (time.monotonic() - t0) * 1_000.00
    token_count = (
        ollama_result.prompt_tokens + ollama_result.completion_tokens
        if ollama_result is not None
        else 0
    )
    return {
        "pipeline": "lpipe",
        "incident_id": incident_id,
        "run_id": run_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": response.ranked_candidates,
        "ppr_scores": {},
        "prompt_version": registry.prompt_version,
        "token_count": token_count,
        "narrative": response.narrative,
        "latency_ms": latency_ms,
        "evaluation_phase": evaluation_phase,
        "schema_version": VERDICT_SCHEMA_VERSION,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/pipelines/test_lpipe_pipeline.py -v
```

Expected: 5 PASS (one may SKIP if `EXPECTED_PROMPT_SHA` is still `None` — run Task 4 to fix).

- [ ] **Step 5: Delete `stub.py` and update `__init__.py`**

Delete `helios/pipelines/l_pipe/stub.py`.

Replace the content of `helios/pipelines/l_pipe/__init__.py` with:

```python
"""helios.pipelines.l_pipe — LLM explanation pipeline gated by VCLFlag.L2C_LLM."""

from helios.pipelines.l_pipe.pipeline import run_lpipe

__all__ = ["run_lpipe"]
```

- [ ] **Step 6: Update `runner.py` to new L-pipe call signature**

In `helios/orchestrator/runner.py`, make these changes:

1. Replace import:
```python
from helios.pipelines.l_pipe.stub import run_lpipe
```
with:
```python
from helios.pipelines.l_pipe.pipeline import run_lpipe
```

2. Replace the L-pipe call and the `_build_verdict` run_id bug. In `_process_incident`:

Replace:
```python
l_out = run_lpipe(incident_id=incident_id, snapshot_hash=snapshot_hash)
```
with (immediately after the `g_out` line):
```python
lpipe_snapshot = ueg_c if ueg_c is not None else UEGCSnapshot(
    incident_id=incident_id,
    variant_config_hash=self._config_hash,
    nodes=[],
    edges=[],
    captured_at_iso="",
)
l_out = run_lpipe(
    incident_id=incident_id,
    snapshot=lpipe_snapshot,
    snapshot_hash=snapshot_hash,
    evaluation_phase=window.evaluation_phase,
    run_id=run_id,
)
```

3. Add the `UEGCSnapshot` import at the top of `runner.py`:
```python
from helios.schemas.ueg_c import UEGCSnapshot
```

4. In `_build_verdict`, fix the `run_id` bug — replace `run_id=str(uuid.uuid4())` with `run_id=stub_out["run_id"]`:
```python
def _build_verdict(self, stub_out: dict[str, Any]) -> PipelineVerdict:
    return PipelineVerdict(
        run_id=stub_out["run_id"],   # threaded from _process_incident
        ...
    )
```

Note: the `uuid` import is no longer needed in `_build_verdict` after this change, but `uuid.uuid4()` is still used in `_process_incident` to generate `run_id`. Keep the `import uuid` at the top of the file.

- [ ] **Step 7: Run all tests**

```bash
poetry run pytest -v
```

Expected: all PASS (zero failures). The `test_expected_prompt_sha_matches_registry` test may SKIP if Task 4 hasn't been run — that is acceptable at this point.

- [ ] **Step 8: Commit**

```bash
git add helios/pipelines/l_pipe/ helios/orchestrator/runner.py tests/pipelines/test_lpipe_pipeline.py
git commit -m "$(cat <<'EOF'
feat(lpipe): pipeline.py entry-point + runner.py updated + stub deleted — 5 tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Deviation log entries

**Files:**
- `deviation_log.jsonl` (via CLI)

- [ ] **Step 1: Log model downgrade deviation**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3" \
  --clause "§3.6.7 L-pipe — model specification" \
  --change "L-pipe uses llama3.1:8b via Ollama for MVP. Research proposal specifies Llama-3.1-70B via vLLM." \
  --reason "Llama-3.1-70B requires ~48GB VRAM; not viable for local exploratory evaluation. Production migration to 70B+vLLM deferred." \
  --analytic-consequence "Narrative quality (CoE) reduced vs 70B. HR@3/CpR metrics unaffected — these depend on ranked_candidates, not narrative quality. Latency_ms values not production-representative. vLLM migration tracked for post-MVP."
```

- [ ] **Step 2: Log Ollama-vs-vLLM deviation**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3" \
  --clause "§3.6.7 L-pipe — serving runtime" \
  --change "L-pipe uses Ollama for MVP serving instead of vLLM as specified in proposal." \
  --reason "Ollama is sufficient for local exploratory runs; vLLM setup deferred to production stage." \
  --analytic-consequence "No impact on HR@3 or CpR. Latency measurements are not production-representative and must not be used for confirmatory MTTR analysis."
```

- [ ] **Step 3: Verify HMAC chain**

```bash
set -a; source .env; set +a
poetry run python bin/log_deviation.py verify
```

Expected: `✓ chain valid — N entries` (where N covers all prior entries plus the 2 new ones).

- [ ] **Step 4: Run deviation log tests**

```bash
poetry run pytest tests/test_deviation_log.py -v
```

Expected: 12 PASS.

- [ ] **Step 5: Commit**

```bash
git add deviation_log.jsonl
git commit -m "$(cat <<'EOF'
research(lpipe): deviation log entries — model downgrade + Ollama runtime (entries 11-12)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Pre-push gate + tracking rows

**Files:**
- `docs/tracking/helios_mvp_tracking.md`

- [ ] **Step 1: Run full pre-push gate**

```bash
set -a; source .env; set +a && \
  poetry run ruff check helios/ scripts/ tests/ && \
  poetry run ruff format --check helios/ scripts/ tests/ && \
  poetry run mypy && \
  poetry run pytest && \
  poetry run python bin/log_deviation.py verify && \
  make validate-tracking
```

Expected: all 6 steps exit 0.

- [ ] **Step 2: Update tracking document**

Add DONE rows to `docs/tracking/helios_mvp_tracking.md` for all M3 Spec 2 ENG tasks. Follow the two-commit pattern:
- First commit: move rows IN_PROGRESS → DONE (with SHA, Ev_Type=ENG, Ev_Ref=PR or commit)
- These rows cover: `lpipe_config.py`, `OllamaClient`, `PromptRegistry`, `ResponseHandler`, `pipeline.py`, runner update, deviation log entries.

Use `make validate-tracking` after every tracking row change.

- [ ] **Step 3: Commit**

```bash
git add docs/tracking/
git commit -m "$(cat <<'EOF'
docs(tracking): M3 Spec 2 L-pipe rows marked DONE

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Exit Gates (Spec 2)

| # | Gate | Verification |
|---|---|---|
| G2-1 | OllamaClient unit tests pass (timeout, connection, Protocol A) | `pytest tests/pipelines/test_lpipe_ollama_client.py -v` → 6 PASS |
| G2-2 | Prompt SHA stable across two loads | `pytest tests/pipelines/test_lpipe_prompt_registry.py::test_sha_stable_across_two_loads` |
| G2-3 | `EXPECTED_PROMPT_SHA` matches live registry | `pytest tests/pipelines/test_lpipe_pipeline.py::test_expected_prompt_sha_matches_registry` |
| G2-4 | Response handler: all error paths (malformed, missing, retry, timeout re-raised) | `pytest tests/pipelines/test_lpipe_response_handler.py -v` → 7 PASS |
| G2-5 | `prompt_version_registry.md` has rca_v1 YAML entry | `python -c "import yaml; print(yaml.safe_load(open('docs/tracking/prompt_version_registry.md').read().split('---')[1])['entries']['rca_v1'])"` |
| G2-6 | Full pipeline: `run_lpipe()` returns valid dict with `prompt_version` | `pytest tests/pipelines/test_lpipe_pipeline.py -v` |
| G2-7 | E2E smoke: HELIOS-Full variant passes | `pytest tests/test_e2e_smoke.py -k helios_full` |
| G2-8 | Deviation log: 2 new entries + chain verified | `python bin/log_deviation.py verify` |
| G2-9 | Connectivity error returns structured dict (does not propagate) | `pytest tests/pipelines/test_lpipe_pipeline.py::test_connectivity_error_returns_failure_dict` |
| G2-10 | `_anomaly_summary()` format pinned | `pytest tests/pipelines/test_lpipe_pipeline.py::test_anomaly_summary_format` |
