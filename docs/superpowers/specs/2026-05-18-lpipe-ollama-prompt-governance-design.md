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

```python
class OllamaClient:
    def __init__(self, base_url: str, model_name: str) -> None: ...
    def generate(self, prompt: str, timeout_s: float) -> str: ...
```

`generate()` raises:
- `OllamaTimeoutError` — request exceeded `timeout_s`
- `OllamaConnectionError` — Ollama not reachable
- `OllamaResponseError` — non-2xx HTTP status

### Protocol A enforcement

Every request includes fixed inference options that enforce deterministic greedy decoding:

```python
payload = {
    "model": self._model_name,
    "prompt": prompt,
    "stream": False,
    "options": {
        "temperature": 0.00,   # greedy — no sampling randomness
        "top_p": 1.00,         # full distribution (temperature=0 makes this irrelevant)
        "top_k": 1,            # greedy top-1 selection
        "seed": LLAMA_SEED,    # from lpipe_config.py; locked in seed_register.md
    },
}
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

**`docs/tracking/prompt_version_registry.md` population:** This document (tracking doc #11, currently schema-only) is populated with the v1 entry on first commit of `rca_v1.txt`. Fields: `prompt_version`, `prompt_sha`, `model_name`, `created_at_iso`, `frozen_at_milestone`.

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

### Handling logic

```
raw_text = ollama_client.generate(prompt)
  → parse JSON
  → validate against LPipeResponse
  → if validation fails AND retries_remaining > 0:
       retry once (LPIPE_MAX_RETRIES = 1)
  → if validation fails after retry:
       return fallback sentinel
```

**Fallback sentinel:**
```python
LPipeResponse(
    ranked_candidates=[],
    narrative="l-pipe-fallback-schema-error",
    confidence=0.00,
)
```

**Error cases handled:**
- Malformed JSON (not parseable): logged, retry triggered
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
```

---

## Pipeline Entry-point (`helios/pipelines/l_pipe/pipeline.py`)

```python
@gated_by(VCLFlag.L2C_LLM)
def run_lpipe(incident_id: str, snapshot_hash: str) -> dict[str, Any]:
    manifest = get_current_manifest()
    registry = PromptRegistry(PROMPT_PATH)
    registry.verify_sha(EXPECTED_PROMPT_SHA)   # tamper-guard; raises if mismatch
    client = OllamaClient(OLLAMA_BASE_URL, MODEL_NAME)
    handler = ResponseHandler(client, max_retries=LPIPE_MAX_RETRIES)
    # Anomaly summary derived from snapshot (service list + narrative stub for M3)
    prompt = registry.render(
        incident_id=incident_id,
        service_list=_service_list_from_snapshot(snapshot_hash),
        anomaly_summary=_anomaly_summary(snapshot_hash),
    )
    response = handler.handle(prompt, timeout_s=TIMEOUT_S)
    return {
        "pipeline": "lpipe",
        "incident_id": incident_id,
        "variant_config_hash": manifest.compute_variant_config_hash(),
        "snapshot_hash": snapshot_hash,
        "ranked_candidates": response.ranked_candidates,
        "ppr_scores": {},             # L-pipe does not produce PPR scores
        "prompt_version": registry.prompt_version,
        "hr_at_3": compute_hr_at_3(response.ranked_candidates, incident_id),
        "cpr": compute_cpr(response.ranked_candidates, incident_id),
        "token_count": _count_tokens(prompt, response),
        "narrative": response.narrative,
        "latency_ms": ...,
        "evaluation_phase": "exploratory",
        "schema_version": "schema-draft-v0.2",
    }
```

**`prompt_version`** in the verdict dict provides a persistent record binding each verdict row to the exact prompt template used. This enables post-hoc audit: if `rca_v1.txt` ever changes, old rows are provably tagged with the old version.

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
