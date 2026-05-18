# L-pipe: Ollama Client + Prompt Governance + Pipeline Design

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this spec task-by-task.

**Goal:** Implement L-pipe with an Ollama-backed LLM client (Protocol A enforcement), a tamper-evident frozen prompt registry, strict JSON response validation with one retry, and a pipeline entry-point replacing the current stub.

**Milestone:** Milestone 3 — Spec 2 of 3
**Date:** 2026-05-18
**Depends on:** Spec 1 (PipelineVerdict schema-draft-v0.2 required — `prompt_version` field added there)
**Blocks:** Spec 3 (OSF freeze requires prompt SHA from this spec)

---

## Pre-conditions

- [ ] Spec 1 merged (PipelineVerdict schema-draft-v0.2 in place)
- [ ] Ollama installed locally: `ollama --version`
- [ ] `llama3.1:8b` pulled: `ollama pull llama3.1:8b`
- [ ] Ollama running: `curl http://localhost:11434/api/tags`
- [ ] `poetry run pytest` green

---

## Architecture Overview

Three independently-testable components assembled by a thin pipeline entry-point:

```
helios/pipelines/l_pipe/
├── ollama_client.py      — model abstraction (Protocol A enforcement)
├── prompt_registry.py    — frozen prompt + SHA256 tamper-guard
├── response_handler.py   — JSON schema validation + single retry + fallback
├── lpipe_config.py       — frozen constants
├── pipeline.py           — assembles above; replaces stub.py
└── prompts/
    └── rca_v1.txt        — frozen prompt template (committed, immutable)
```

---

## Component 1 — OllamaClient (`helios/pipelines/l_pipe/ollama_client.py`)

### Interface

`generate()` returns a structured result, not a bare string. The Ollama API response body includes `prompt_eval_count` (tokens in prompt) and `eval_count` (tokens generated) — these are required for the verdict `token_count` field and for latency auditing:

```python
@dataclass(frozen=True)
class OllamaGenerateResult:
    text: str
    prompt_tokens: int       # from Ollama response["prompt_eval_count"]
    completion_tokens: int   # from Ollama response["eval_count"]

class OllamaClient:
    def __init__(self, base_url: str, model_name: str) -> None: ...
    def generate(self, prompt: str, timeout_s: float) -> OllamaGenerateResult: ...
```

`generate()` raises:
- `OllamaTimeoutError` — request exceeded `timeout_s`
- `OllamaConnectionError` — Ollama not reachable
- `OllamaResponseError` — non-2xx HTTP status

### Protocol A enforcement

Every request includes fixed inference options that enforce deterministic greedy decoding. The `"format": "json"` key instructs Ollama to enforce JSON-only output mode at the server level — this reduces (but does not eliminate) markdown-wrapping of responses:

```python
payload = {
    "model": self._model_name,
    "prompt": prompt,
    "stream": False,
    "format": "json",          # server-side JSON enforcement
    "options": {
        "temperature": 0.00,   # greedy — no sampling randomness
        "top_p": 1.00,         # full distribution (temperature=0 makes this irrelevant)
        "top_k": 1,            # greedy top-1 selection
        "seed": LLAMA_SEED,    # from lpipe_config.py; locked in seed_register.md
    },
}
```

The response body carries token counts:
```python
body = response.json()
return OllamaGenerateResult(
    text=body["response"],
    prompt_tokens=body.get("prompt_eval_count", 0),
    completion_tokens=body.get("eval_count", 0),
)
```

These options are not configurable at call time. Any change to these values requires a deviation log entry (Protocol A violation). Record in `lpipe_config.py` as named constants so the deviation log can cite exact values.

**Deviation entry (model downgrade):**
```bash
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3" \
  --clause "§3.6.7 L-pipe — model specification" \
  --change "L-pipe uses llama3.1:8b via Ollama for MVP. Research proposal specifies Llama-3.1-70B via vLLM." \
  --reason "Llama-3.1-70B requires ~48GB VRAM; not viable for local exploratory evaluation. Production migration to 70B+vLLM deferred." \
  --analytic-consequence "Narrative quality (CoE) reduced vs 70B. HR@3/CpR metrics unaffected — these depend on ranked_candidates, not narrative quality. Latency_ms values not production-representative. vLLM migration tracked for post-MVP."
```

**Deviation entry (Ollama vs vLLM):**
```bash
poetry run python bin/log_deviation.py \
  --stage "Stage 1 / M3" \
  --clause "§3.6.7 L-pipe — serving runtime" \
  --change "L-pipe uses Ollama for MVP serving instead of vLLM as specified in proposal." \
  --reason "Ollama is sufficient for local exploratory runs; vLLM setup deferred to production stage." \
  --analytic-consequence "No impact on HR@3 or CpR. Latency measurements are not production-representative and must not be used for confirmatory MTTR analysis."
```

### Tests (`tests/pipelines/test_lpipe_ollama_client.py`)

| Test | Scenario |
|---|---|
| `test_generate_returns_response_on_success` | Mock HTTP 200 → returns response text |
| `test_generate_raises_timeout` | HTTP timeout → `OllamaTimeoutError` |
| `test_generate_raises_connection_error` | Ollama not reachable → `OllamaConnectionError` |
| `test_generate_raises_on_non_2xx` | HTTP 500 → `OllamaResponseError` |
| `test_protocol_a_options_always_sent` | Assert `temperature`, `top_p`, `top_k`, `seed` present in every request |
| `test_protocol_a_options_not_overridable` | Confirm no `generate()` param can change these options |

---

## Component 2 — PromptRegistry (`helios/pipelines/l_pipe/prompt_registry.py`)

### Frozen prompt file

`helios/pipelines/l_pipe/prompts/rca_v1.txt` — committed to git. The prompt template uses `{incident_id}`, `{service_list}`, `{anomaly_summary}` as the only placeholders. No other substitutions permitted.

### SHA governance

```python
class PromptRegistry:
    def __init__(self, prompt_path: Path) -> None:
        self._text = prompt_path.read_text(encoding="utf-8")
        self._sha = hashlib.sha256(self._text.encode()).hexdigest()

    @property
    def prompt_sha(self) -> str:
        return self._sha

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION  # from lpipe_config.py

    def render(self, *, incident_id: str, service_list: list[str],
               anomaly_summary: str) -> str:
        return self._text.format(
            incident_id=incident_id,
            service_list=", ".join(service_list),
            anomaly_summary=anomaly_summary,
        )

    def verify_sha(self, expected_sha: str) -> bool:
        return self._sha == expected_sha
```

**Tamper-guard:** `verify_sha()` is called on every pipeline instantiation. If the SHA diverges from the value recorded in `docs/tracking/prompt_version_registry.md`, the pipeline raises `PromptTamperError` and halts. This prevents silent prompt drift.

**`docs/tracking/prompt_version_registry.md` population:** This document (tracking doc #11, currently schema-only) is populated with the v1 entry on first commit of `rca_v1.txt`. It must use **YAML front-matter** (the structured block before the first `---` separator) because `verify_osf_freeze.py` parses it with `yaml.safe_load()` — free-form Markdown table rows are not acceptable. Required structure:

```markdown
---
entries:
  rca_v1:
    prompt_version: "rca_v1"
    prompt_sha256: "<64-char hex of rca_v1.txt>"
    model_name: "llama3.1:8b"
    created_at_iso: "<ISO 8601 timestamp>"
    frozen_at_milestone: "Milestone 3"
---

# Prompt Version Registry

Human-readable notes below the separator are ignored by the parser.
```

The `prompt_sha256` field must match the SHA256 computed by `PromptRegistry` on `rca_v1.txt`. After populating this file, verify: `poetry run python -c "import yaml; print(yaml.safe_load(open('docs/tracking/prompt_version_registry.md').read().split('---')[1])['entries']['rca_v1'])"` — this must not raise.

### Tests (`tests/pipelines/test_lpipe_prompt_registry.py`)

| Test | Scenario |
|---|---|
| `test_sha_stable_across_two_loads` | Load prompt twice → identical SHA |
| `test_render_substitutes_placeholders` | All three placeholders substituted correctly |
| `test_verify_sha_passes_on_correct_hash` | Known hash → `verify_sha` returns True |
| `test_verify_sha_fails_on_tampered_content` | Modified text → SHA mismatch → False |
| `test_tamper_raises_on_pipeline_init` | SHA mismatch → `PromptTamperError` raised |

---

## Component 3 — ResponseHandler (`helios/pipelines/l_pipe/response_handler.py`)

### Output schema (`LPipeResponse` Pydantic model)

```python
class LPipeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ranked_candidates: list[str]   # ordered, non-empty
    narrative: str                 # CoE text, non-empty
    confidence: float = Field(ge=0, le=1)
```

### Sanitization utility

Even with `"format": "json"` set on the Ollama request, some models wrap the JSON in markdown fences. `sanitize_llm_output()` must be called before any JSON parsing attempt:

```python
import re

_MD_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

def sanitize_llm_output(raw: str) -> str:
    """Strip markdown code-block wrappers if present; return raw unchanged otherwise."""
    m = _MD_FENCE_RE.search(raw)
    if m:
        return m.group(1).strip()
    return raw.strip()
```

### Handling logic

```
result = ollama_client.generate(prompt)   # OllamaGenerateResult
  → sanitize_llm_output(result.text)
  → parse JSON
  → validate against LPipeResponse
  → if validation fails AND retries_remaining > 0:
       retry once (LPIPE_MAX_RETRIES = 1)
  → if validation fails after retry:
       return fallback sentinel
```

**Fallback sentinel:** `handle()` always returns a two-element tuple `(LPipeResponse, OllamaGenerateResult | None)`. On retry exhaustion fallback, the second element is `None` (no successful Ollama round-trip):

```python
fallback_response = LPipeResponse(
    ranked_candidates=["l-pipe-fallback"],   # non-empty — PipelineVerdict min_length safe
    narrative="l-pipe-fallback-schema-error",
    confidence=0.00,
)
return (fallback_response, None)   # ← always a tuple; second element None on fallback
```

Connectivity errors (`OllamaTimeoutError`, `OllamaConnectionError`, `OllamaResponseError`) are **not caught inside `handle()`** — they propagate to `run_lpipe()`'s `try/except` block, which produces a structured failure dict. The `handle()` → `run_lpipe()` interface is therefore: `handle()` returns a tuple on success OR fallback; connectivity errors propagate as exceptions. This split avoids merging two fundamentally different failure modes (schema/validation failure vs. network failure) into a single return path.

`ranked_candidates=["l-pipe-fallback"]` is used instead of an empty list because `PipelineVerdict` (and any downstream metric validation) may enforce `min_length=1` on `ranked_candidates`. The sentinel string is recognisable and can be filtered in evaluation scripts analogously to the G-pipe sentinel.

**Error cases handled:**
- Malformed JSON (not parseable): sanitize then retry; log original text on failure
- Markdown-wrapped JSON: sanitized by `sanitize_llm_output()` before parsing
- Missing required field: Pydantic ValidationError, retry triggered
- Schema mismatch (extra field blocked by `extra="forbid"`): retry triggered
- Retry exhaustion: fallback returned, not raised
- Timeout / connection error: re-raised (not swallowed) — caller decides

### Tests (`tests/pipelines/test_lpipe_response_handler.py`)

| Test | Scenario |
|---|---|
| `test_valid_response_parsed_correctly` | Valid JSON → `LPipeResponse` returned |
| `test_malformed_json_triggers_retry` | Non-JSON text → retry → valid on second attempt |
| `test_missing_field_triggers_retry` | Missing `narrative` → retry → fallback after second failure |
| `test_retry_exhaustion_returns_fallback` | Two consecutive failures → fallback sentinel returned |
| `test_timeout_is_reraised` | `OllamaTimeoutError` propagates (not swallowed) |
| `test_extra_field_rejected` | Extra field in response → ValidationError → retry |

---

## Component 4 — lpipe_config.py

```python
from helios.vcl import VCLFlag  # noqa: F401 — satisfies flag-guard

OLLAMA_BASE_URL: str = "http://localhost:11434"
MODEL_NAME: str = "llama3.1:8b"
TIMEOUT_S: float = 120.00
LPIPE_MAX_RETRIES: int = 1
PROMPT_VERSION: str = "rca_v1"

# Protocol A — greedy decoding; frozen. Change requires deviation log entry.
PROTOCOL_A_TEMPERATURE: float = 0.00
PROTOCOL_A_TOP_P: float = 1.00
PROTOCOL_A_TOP_K: int = 1
LLAMA_SEED: int = 42   # locked in seed_register.md; do not change

# SHA-256 of prompts/rca_v1.txt — computed on first commit and frozen.
# run_lpipe() calls registry.verify_sha(EXPECTED_PROMPT_SHA) on every invocation.
# Changing this constant requires a deviation log entry (Protocol A violation).
EXPECTED_PROMPT_SHA: str = "<64-char hex — compute with: sha256sum helios/pipelines/l_pipe/prompts/rca_v1.txt>"
```

---

## Pipeline Entry-point (`helios/pipelines/l_pipe/pipeline.py`)

**Signature:** `run_lpipe` accepts the full `UEGCSnapshot` object — not just `snapshot_hash` — so that `_service_list_from_snapshot()` and `_anomaly_summary()` can read service names and anomaly data directly from the in-memory snapshot rather than re-loading from disk via hash lookup:

```python
@gated_by(VCLFlag.L2C_LLM)
def run_lpipe(
    incident_id: str,
    snapshot: UEGCSnapshot,
    snapshot_hash: str,
    evaluation_phase: str,   # passed from orchestrator; never hardcoded
) -> dict[str, Any]:
    t0 = time.monotonic()
    manifest = get_current_manifest()
    registry = PromptRegistry(PROMPT_PATH)
    registry.verify_sha(EXPECTED_PROMPT_SHA)   # tamper-guard; raises if mismatch
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
        # Catches all three Ollama failure modes:
        #   OllamaTimeoutError    — request exceeded timeout_s
        #   OllamaConnectionError — Ollama not reachable (network/container)
        #   OllamaResponseError   — non-2xx HTTP (5xx gateway error, model load failure)
        # All three must be caught here. OllamaResponseError propagating to the
        # orchestrator would crash the E2E run for a server-side failure that is no
        # more fatal than a timeout. Log and return structured failure payload.
        latency_ms = (time.monotonic() - t0) * 1000.0
        import logging
        logging.getLogger(__name__).error(
            "lpipe transient error for %s: %s", incident_id, exc
        )
        return {
            "pipeline": "lpipe",
            "incident_id": incident_id,
            "variant_config_hash": manifest.compute_variant_config_hash(),
            "snapshot_hash": snapshot_hash,
            "ranked_candidates": ["l-pipe-connectivity-error"],
            "ppr_scores": {},
            "prompt_version": registry.prompt_version,
            "token_count": 0,
            "narrative": f"l-pipe-connectivity-error: {type(exc).__name__}",
            "latency_ms": latency_ms,
            "evaluation_phase": evaluation_phase,
            "schema_version": VERDICT_SCHEMA_VERSION,  # imported from helios.schemas.verdict
        }
    latency_ms = (time.monotonic() - t0) * 1000.0
    token_count = (
        ollama_result.prompt_tokens + ollama_result.completion_tokens
        if ollama_result is not None else 0
    )
    return {
        "pipeline": "lpipe",
        "incident_id": incident_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": response.ranked_candidates,
        "ppr_scores": {},             # L-pipe does not produce PPR scores
        "prompt_version": registry.prompt_version,
        "token_count": token_count,
        "narrative": response.narrative,
        "latency_ms": latency_ms,
        "evaluation_phase": evaluation_phase,   # passed from orchestrator; never hardcoded
        "schema_version": VERDICT_SCHEMA_VERSION,  # imported from helios.schemas.verdict
    }
```

**`hr_at_3` and `cpr` are not computed inside `run_lpipe`** — pipelines output raw `ranked_candidates` and `narrative` only. Metric computation (`hr_at_3`, `cpr`) belongs in the evaluation harness (`scripts/evaluate_ablation.py`) which has access to ground truth.

**Schema consequence:** `PipelineVerdict` v0.2 must give `hr_at_3` and `cpr` default values so that pipeline-returned dicts (which omit them) are accepted by Pydantic without a `ValidationError`:

```python
hr_at_3: float = Field(default=0.0, ge=0, le=1)   # populated by eval harness
cpr: float = Field(default=0.0, ge=0, le=1)         # populated by eval harness
```

Without defaults, `PipelineVerdict(**run_lpipe(...))` raises immediately because both fields are required but absent from the dict. This change is part of the v0.2 schema definition in Spec 1 (§3.1) and must be included in the `PipelineVerdict` update there. The evaluation harness computes real values from `ranked_candidates` + ground truth and either patches the stored row or records metrics in a separate aggregation table.

**Return type contract — `run_lpipe()` always returns `dict[str, Any]`.** The `handler.handle()` returns `tuple[LPipeResponse, OllamaGenerateResult | None]` — but `run_lpipe()` is a pipeline entry-point that always returns a plain dict, never a tuple. The three paths are: (a) success — unpack handler tuple, build dict; (b) retry-exhaustion fallback — handler returns `(sentinel_response, None)` tuple, pipeline builds dict from it; (c) connectivity error — exception propagates from `handler.handle()` to `run_lpipe()`'s `try/except`, which builds and returns a dict. None of these paths produce a tuple at the `run_lpipe()` level. The orchestrator unpacks `run_lpipe()` as a dict — a tuple return would crash `dpipe_verdict.get(...)` upstream.

Add `from helios.schemas.verdict import VERDICT_SCHEMA_VERSION` at the top of `pipeline.py` — both the connectivity error path and the success path use this constant in their return dicts.

**`token_count`** is derived from `OllamaGenerateResult.prompt_tokens + completion_tokens`. `ResponseHandler.handle()` must return `tuple[LPipeResponse, OllamaGenerateResult | None]` in **all cases** — including retry exhaustion fallback. On fallback, the second element is `None` (no Ollama round-trip succeeded). The pipeline unpacks safely:

```python
response, ollama_result = handler.handle(prompt, timeout_s=TIMEOUT_S)
token_count = (
    ollama_result.prompt_tokens + ollama_result.completion_tokens
    if ollama_result is not None else 0
)
```

Returning a bare `LPipeResponse` on fallback (as a single object, not a tuple) causes `ValueError: not enough values to unpack` at the call site. The `handle()` return type must be `tuple[LPipeResponse, OllamaGenerateResult | None]` unconditionally — the two-element tuple invariant never breaks regardless of path taken through the error-handling logic.

**`prompt_version`** in the verdict dict provides a persistent record binding each verdict row to the exact prompt template used. This enables post-hoc audit: if `rca_v1.txt` ever changes, old rows are provably tagged with the old version.

**Snapshot utility helpers — declared in `pipeline.py`:** `_service_list_from_snapshot` and `_anomaly_summary` are not imported from an external module. They are defined locally in `pipeline.py` using only `UEGCSnapshot`'s existing fields (`nodes: list[UEGCNode]`, `edges: list[UEGCEdge]`):

```python
from helios.schemas.ueg_c import UEGCSnapshot

def _service_list_from_snapshot(snapshot: UEGCSnapshot) -> list[str]:
    """Sorted unique service names from graph nodes — used as L-pipe prompt input."""
    return sorted({node.service_name for node in snapshot.nodes})

def _anomaly_summary(snapshot: UEGCSnapshot) -> str:
    """Stub anomaly summary for M3 — service names only; no live metric inference.

    Production upgrade: derive from D-pipe AnomalyScorer output passed through
    the orchestrator. Deferred to post-M3.
    """
    services = _service_list_from_snapshot(snapshot)
    return f"Anomalies detected across {len(services)} services: {', '.join(services)}"
```

These helpers contain no inference logic and require no external imports beyond `UEGCSnapshot`. The `_anomaly_summary` stub is intentionally minimal for M3 — it documents the production upgrade path without blocking the protocol freeze.

**Test for `EXPECTED_PROMPT_SHA` runtime match (mandatory tamper-guard verification):**

```python
def test_expected_prompt_sha_matches_registry():
    """EXPECTED_PROMPT_SHA in lpipe_config.py must match the live file SHA.

    If this test fails: the prompt file changed without updating the constant,
    OR the constant was changed without updating the file. Either requires a
    deviation log entry before the test can be updated.
    """
    from helios.pipelines.l_pipe.lpipe_config import EXPECTED_PROMPT_SHA
    from helios.pipelines.l_pipe.prompt_registry import PromptRegistry, PROMPT_PATH

    registry = PromptRegistry(PROMPT_PATH)
    assert registry.prompt_sha == EXPECTED_PROMPT_SHA, (
        f"Prompt SHA mismatch: live={registry.prompt_sha!r} "
        f"frozen={EXPECTED_PROMPT_SHA!r}"
    )
```

**Compute `EXPECTED_PROMPT_SHA` on first commit of `rca_v1.txt`:**
```bash
sha256sum helios/pipelines/l_pipe/prompts/rca_v1.txt | cut -d' ' -f1
```
Paste the 64-char hex into `lpipe_config.py`. Run `poetry run pytest tests/pipelines/test_lpipe_pipeline.py::test_expected_prompt_sha_matches_registry -v` to confirm.

**Prompt rendering SHA stability test (integration):** The rendered prompt feeds into SHA computation — a format change to `_anomaly_summary()` or `PromptRegistry.render()` will change the rendered string and thus the post-render SHA. Pin this with an integration test:

```python
def test_prompt_rendering_sha_is_stable():
    """Rendered prompt SHA must match expected value.

    Protects against: rca_v1.txt edits, _anomaly_summary() format changes,
    service_list ordering changes. All three alter the final rendered string
    and would invalidate the OSF freeze if undetected.
    """
    from helios.pipelines.l_pipe.prompt_registry import PromptRegistry, PROMPT_PATH
    from helios.pipelines.l_pipe.pipeline import _anomaly_summary, _service_list_from_snapshot
    import hashlib

    snapshot = _make_test_snapshot(["svcA", "svcB"])  # fixture: 2-node UEGCSnapshot
    registry = PromptRegistry(PROMPT_PATH)
    rendered = registry.render(
        incident_id="test-001",
        service_list=_service_list_from_snapshot(snapshot),
        anomaly_summary=_anomaly_summary(snapshot),
    )
    rendered_sha = hashlib.sha256(rendered.encode()).hexdigest()
    # Compute expected once; freeze it. Any change → deviation log first.
    EXPECTED_RENDERED_SHA = "<compute on first test run>"
    assert rendered_sha == EXPECTED_RENDERED_SHA
```

**Test for `_anomaly_summary` string stability (mandatory for prompt SHA):** The prompt SHA is computed from the rendered prompt, which includes `_anomaly_summary()` output. If the output format changes, the rendered prompt changes, and the SHA diverges from the frozen registry value — triggering `PromptTamperError`. Pin the expected output format with an explicit test:

```python
def test_anomaly_summary_format():
    snapshot = UEGCSnapshot(nodes=[
        UEGCNode(service_name="svcA", ...),
        UEGCNode(service_name="svcB", ...),
    ], edges=[])
    result = _anomaly_summary(snapshot)
    assert result == "Anomalies detected across 2 services: svcA, svcB"
```

This test must live in `tests/pipelines/test_lpipe_pipeline.py` and import `_anomaly_summary` from `helios.pipelines.l_pipe.pipeline`. Any change to the format string in `_anomaly_summary` requires a deviation log entry (prompt governance violation) before the test can be updated.

---

## Exit Gates (Spec 2)

| # | Gate | Evidence artefact |
|---|---|---|
| G2-1 | `OllamaClient` unit tests pass (timeout, connection, Protocol A options) | `pytest tests/pipelines/test_lpipe_ollama_client.py -v` |
| G2-2 | Prompt SHA stable across two loads | `pytest tests/pipelines/test_lpipe_prompt_registry.py::test_sha_stable_across_two_loads` |
| G2-3 | Prompt SHA matches live registry on every pipeline run (integration test) | `pytest tests/pipelines/test_lpipe_pipeline.py::test_prompt_sha_matches_registry` |
| G2-4 | Response handler: all error paths handled (malformed, missing, retry exhaustion, timeout re-raised) | `pytest tests/pipelines/test_lpipe_response_handler.py -v` |
| G2-5 | `prompt_version_registry.md` populated with `rca_v1` entry (SHA, model, date) | Manual review of file |
| G2-6 | Full pipeline: `run_lpipe()` returns valid `PipelineVerdict`-compatible dict with `prompt_version` set | `pytest tests/pipelines/test_lpipe_pipeline.py -v` |
| G2-9 | Transient error path: `OllamaConnectionError` returns structured failure dict (does not propagate) | `pytest tests/pipelines/test_lpipe_pipeline.py::test_connectivity_error_returns_failure_dict` |
| G2-10 | `_anomaly_summary()` produces expected string format for prompt rendering | `pytest tests/pipelines/test_lpipe_pipeline.py::test_anomaly_summary_format` |
| G2-7 | E2E smoke: HELIOS-Full variant (D + G + L all active) | `pytest tests/test_e2e_smoke.py -k helios_full` |
| G2-8 | Deviation log: model downgrade + Ollama vs vLLM entries added and chain verified | `bin/log_deviation.py verify` |

---

## Files Modified / Created

| File | Action |
|---|---|
| `helios/pipelines/l_pipe/stub.py` | **Delete** |
| `helios/pipelines/l_pipe/__init__.py` | Update export |
| `helios/pipelines/l_pipe/pipeline.py` | **New** — assembles all components |
| `helios/pipelines/l_pipe/ollama_client.py` | **New** — Protocol A model abstraction |
| `helios/pipelines/l_pipe/prompt_registry.py` | **New** — SHA governance |
| `helios/pipelines/l_pipe/response_handler.py` | **New** — JSON validation + single retry + fallback |
| `helios/pipelines/l_pipe/lpipe_config.py` | **New** — frozen constants |
| `helios/pipelines/l_pipe/prompts/rca_v1.txt` | **New** — frozen prompt template |
| `docs/tracking/prompt_version_registry.md` | Populate v1 entry |
| `tests/pipelines/test_lpipe_ollama_client.py` | **New** |
| `tests/pipelines/test_lpipe_prompt_registry.py` | **New** |
| `tests/pipelines/test_lpipe_response_handler.py` | **New** |
| `tests/pipelines/test_lpipe_pipeline.py` | **New** |
