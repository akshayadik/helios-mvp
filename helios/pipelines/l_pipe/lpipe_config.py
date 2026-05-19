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
