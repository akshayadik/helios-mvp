"""Service, component and flag aliasing for L-pipe prompts (S2.3 design L-i)."""

from __future__ import annotations

import pytest

from helios.adapters.otel_campaign import FAULTS
from helios.pipelines.l_pipe.aliases import (
    FEATURE_FLAG_NAMES,
    AliasLeakError,
    build_alias_map,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

OTEL = [
    "ad",
    "cart",
    "checkout",
    "frontend",
    "frontend-proxy",
    "payment",
    "product-catalog",
    "recommendation",
]


def test_same_incident_same_map() -> None:
    a = build_alias_map("abc123", OTEL, [])
    b = build_alias_map("abc123", list(reversed(OTEL)), [])
    assert dict(a.forward) == dict(b.forward)
    assert sorted(a.forward[s] for s in OTEL) == [f"svc-0{i}" for i in range(1, 9)]


def test_different_incidents_differ() -> None:
    a = build_alias_map("incident-one", OTEL, [])
    b = build_alias_map("incident-two", OTEL, [])
    assert dict(a.forward) != dict(b.forward)


def test_spelling_variants_masked() -> None:
    m = build_alias_map("x", OTEL, [])
    alias = m.forward["checkout"]
    text = (
        "checkout checkoutservice checkout-service CheckoutService "
        "hipstershop.CheckoutService/PlaceOrder http://checkout:8080/api/checkout "
        "pod checkout-7d9f CHECKOUT"
    )
    masked = m.mask(text)
    assert "checkout" not in masked.lower()
    assert masked.count(alias) == 9
    assert "PlaceOrder" in masked


def test_short_stem_respects_boundaries() -> None:
    m = build_alias_map("x", OTEL, [])
    alias = m.forward["ad"]
    masked = m.mask("AdService adservice ad-service ad:9555 address load header GetAds")
    assert masked.split() == [
        alias,
        alias,
        alias,
        f"{alias}:9555",
        "address",
        "load",
        "header",
        "GetAds",
    ]


def test_longest_name_first() -> None:
    m = build_alias_map("x", OTEL, [])
    masked = m.mask("frontend-proxy calls frontend")
    assert masked == f"{m.forward['frontend-proxy']} calls {m.forward['frontend']}"


def test_components_and_flags_masked() -> None:
    m = build_alias_map("x", OTEL, ["redis", "otel-collector"])
    masked = m.mask("paymentFailure flag on; redis timeout; otel-collector up")
    assert m.forward["paymentFailure"].startswith("flag-")
    assert m.forward["redis"].startswith("dep-")
    assert "payment" not in masked.lower()
    assert "redis" not in masked and "collector" not in masked


def test_check_refuses_survivor() -> None:
    m = build_alias_map("x", OTEL, [])
    m.check(m.mask("cart failed to reach checkout"))
    with pytest.raises(AliasLeakError) as err:
        m.check("cart failed")
    assert "cart" not in str(err.value)


def test_flag_list_matches_campaign_catalogue() -> None:
    assert {f.flag for f in FAULTS} == FEATURE_FLAG_NAMES


def test_unmask_round_trip() -> None:
    m = build_alias_map("x", OTEL, ["redis"])
    for real, alias in m.forward.items():
        assert m.unmask(alias) == real
    with pytest.raises(KeyError):
        m.unmask("svc-99")
