"""HELIOS API (S4.1, design docs/sprints/s4-product-eval-tooling/s4_1_api_design.md).

Read stored verdicts and record human decisions on them. Runs are started by
the CLI, never through the API (design A-b). The API never returns ground
truth or anything derived from it (HR@k, TTCD, CpR).
"""

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_API: bool = True
# S4.2 approval console: off removes GET /v1/queue (and compose's console).
HELIOS_ENABLE_CONSOLE: bool = True
API_VERSION = (
    "api-v1.2"  # S4.5-S4.7: additive (action, control_plane_degraded, shadow mode)
)
