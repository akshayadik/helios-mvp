"""Out-of-scope service list (S2.1, owner decision D-f)."""

from __future__ import annotations

from helios.telemetry.scope import (
    OUT_OF_SCOPE_SERVICES,
    filter_in_scope,
    in_scope,
    scope_digest,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance


def test_out_of_scope_list_is_the_frozen_list() -> None:
    assert (
        frozenset(
            {
                "load-generator",
                "flagd",
                "flagd-ui",
                "prometheus",
                "jaeger",
                "opensearch",
                "grafana",
                "otel-collector",
                "otelcol-contrib",
            }
        )
        == OUT_OF_SCOPE_SERVICES
    )


def test_filter_keeps_order_and_drops_harness_and_observability() -> None:
    assert filter_in_scope(["prometheus", "cart", "load-generator", "ad"]) == [
        "cart",
        "ad",
    ]


def test_app_dependencies_stay_in_scope() -> None:
    assert all(in_scope(s) for s in ("kafka", "valkey-cart", "postgresql"))


def test_names_match_loosely_as_scoring_does() -> None:
    assert not in_scope("OTel-Collector")
    assert not in_scope("loadGeneratorService")
    assert in_scope("frontend")


def test_scope_digest_is_stable() -> None:
    assert scope_digest() == scope_digest()
    assert len(scope_digest()) == 64


def test_collector_is_out_of_scope_under_its_log_name() -> None:
    # The collector's own logs carry resource service.name "otelcol-contrib"
    # (seen once log attribution was fixed, S2-M7-ENG10); same component as D-f.
    assert not in_scope("otelcol-contrib")
