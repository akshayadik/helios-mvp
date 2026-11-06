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
EXPECTED_PROMPT_SHA: str | None = (
    "376e555b0bd07a14667c9d5f09275ce5507ddce443fa01781bd7dc40a9365e47"
)

# S2.3 workers (design §5.2 to §5.4); fixed in the pre-work deviation entry.
DIGEST_TOKEN_CAP: int = 2000  # per worker digest, tokens = ceil(characters / 4)
METRIC_LINES_PER_SERVICE: int = 3
ONSET_UNITS: int = 3  # a metric line names when a series first moved this far
MAX_RANKED: int = 5
LOG_LINES_PER_SERVICE: int = 4
LOG_RISE_FACTOR: int = 2  # a template is listed when its rate at least doubles
TEMPLATE_CHARS: int = 160
TRACE_LINES_PER_SERVICE: int = 4
TRACE_MIN_SPANS: int = (
    3  # spans on each side of the trigger before a median is compared
)
TRACE_RISE_FACTOR: int = 2
# P2 written by the OTel capture: the only trace format build data validated (L-f).
TRACE_VALIDATED_ROOTS: tuple[str, ...] = ("data/otel",)
# SHA-256 of prompts/<worker>_v1.txt, frozen with deviation entry 58 (round 1
# prompts; build report calibration/lpipe_round3.json). A change needs a new
# entry; a confirmatory run refuses provisional (None) or changed prompts.
WORKER_PROMPT_SHAS: dict[str, str | None] = {
    "metric": "99c7c10e83ec4712b91feb9d53568d500a9383fb3f666d7ce689c55723e36b6b",
    "log": "da32233962d114908164eed606240b7fa582a4bd5b3d8fce201750464d536735",
    "trace": "c59b9a99769cc61b8154e89f981be5df939f677d83b96c0c48ca50c389915c9e",
}
# Ollama digest of the served llama3.1:8b (entry 58); checked at run start.
EXPECTED_MODEL_DIGEST: str | None = (
    "46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e"
)
LOG_MIN_LINES: int = 3  # lines after the trigger before a template is listed
