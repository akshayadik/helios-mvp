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
