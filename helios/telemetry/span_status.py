"""One rule for "this span is an error", shared by HELIOS and the baselines.

Deviation entry 104 (phase E day-one check): the confirmatory pool's traces
carry gRPC status codes, the OTel demo's carry OTel text. Before the entry,
HELIOS (G-pipe span features, L-pipe digests) and the baseline export each
had their own rule and each missed part of the pool's errors.

A span is an error when its status is

- ``ERROR`` or ``STATUS_CODE_ERROR`` (OTel text, any case);
- an integer from 2 to 16: the gRPC codes other than OK (0) and CANCELLED
  (1); 2 is also OTel's enum value for ERROR;
- an integer of at least 400 (HTTP).

Everything else is not an error: empty, ``UNSET``, ``OK``, 0, 1 (OTel OK or
gRPC CANCELLED) and any other value. On build data (OTel text only) the rule
gives the same answer as both rules it replaces.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

__all__ = [
    "ERROR_TEXT",
    "GRPC_ERROR_CODES",
    "HTTP_ERROR_FROM",
    "error_mask",
    "is_error_status",
]

ERROR_TEXT = frozenset({"ERROR", "STATUS_CODE_ERROR"})
GRPC_ERROR_CODES = range(2, 17)
HTTP_ERROR_FROM = 400


def is_error_status(status: Any) -> bool:
    """True when one span status counts as an error (rule in the module docstring)."""
    if status is None or (isinstance(status, float) and pd.isna(status)):
        return False
    text = str(status).strip().upper()
    if text in ERROR_TEXT:
        return True
    if not text.isdigit():
        return False
    code = int(text)
    return code in GRPC_ERROR_CODES or code >= HTTP_ERROR_FROM


def error_mask(statuses: pd.Series) -> pd.Series:
    """Element-wise ``is_error_status`` over a column of statuses (missing = not an error)."""
    text = statuses.astype("string").fillna("").str.strip().str.upper()
    digits = text.str.fullmatch(r"\d+").fillna(False).astype(bool)
    codes = pd.to_numeric(text.where(digits), errors="coerce")
    numeric = codes.between(min(GRPC_ERROR_CODES), max(GRPC_ERROR_CODES)) | (
        codes >= HTTP_ERROR_FROM
    )
    return (text.isin(ERROR_TEXT) | (digits & numeric.fillna(False))).astype(bool)
