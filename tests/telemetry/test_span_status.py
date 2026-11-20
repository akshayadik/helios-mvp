"""The shared span-error rule (deviation entry 104)."""

from __future__ import annotations

import pandas as pd
import pytest

from helios.graph.span_features import _is_error
from helios.telemetry.span_status import error_mask, is_error_status
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

# Every value found in the pool traces by the day-one check, and in build data.
POOL_ERRORS = ["2", "4", "9", "12", "13", "14", "400"]
POOL_NOT_ERRORS = ["", "0"]
BUILD_VALUES = {"UNSET": False, "OK": False, "ERROR": True}


@pytest.mark.parametrize("value", POOL_ERRORS)
def test_pool_error_codes_count(value: str) -> None:
    assert is_error_status(value)


@pytest.mark.parametrize("value", POOL_NOT_ERRORS)
def test_pool_ok_and_unset_do_not_count(value: str) -> None:
    assert not is_error_status(value)


def test_otel_text_any_case() -> None:
    assert is_error_status("error") and is_error_status(" STATUS_CODE_ERROR ")
    assert not is_error_status("STATUS_CODE_OK") and not is_error_status("UNSET")


def test_edges_of_the_numeric_ranges() -> None:
    assert not is_error_status("1")  # OTel OK or gRPC CANCELLED
    assert is_error_status("16") and not is_error_status("17")
    assert not is_error_status("399") and is_error_status("503")
    assert not is_error_status("-14") and not is_error_status("14.0")


def test_missing_values_are_not_errors() -> None:
    assert not is_error_status(None) and not is_error_status(float("nan"))


def test_build_data_unchanged_against_both_old_rules() -> None:
    old_helios = {"2", "ERROR", "STATUS_CODE_ERROR"}
    for value, expected in BUILD_VALUES.items():
        assert is_error_status(value) is expected
        assert (value in old_helios) is expected


def test_mask_matches_the_scalar_rule() -> None:
    values = [*POOL_ERRORS, *POOL_NOT_ERRORS, *BUILD_VALUES, "1", "17", "abc", None]
    mask = error_mask(pd.Series(values, dtype="object"))
    assert mask.dtype == bool
    assert mask.tolist() == [is_error_status(v) for v in values]


def test_mask_on_an_integer_column() -> None:
    mask = error_mask(pd.Series([0, 2, 14, 200, 500]))
    assert mask.tolist() == [False, True, True, False, True]


def test_gpipe_span_features_use_the_shared_rule() -> None:
    assert _is_error({"status_code": "14"}) and not _is_error({"status_code": "0"})
    assert not _is_error({})
