"""Action-Class Predictor (Ch3 Algorithm 2; S3.2, row S2-M8-ENG02).

Gated by ``VCLFlag.ACP_STATEFUL`` (OFF = HELIOS-noACP, uniform prior).
Exploratory in Stage A: recorded in the CoE routing step, never read by the
frozen router or cited by the narrator (design ``s3_2_acp_design.md``).
"""

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

HELIOS_ENABLE_ACP: bool = True
