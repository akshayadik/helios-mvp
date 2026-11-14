"""PII redaction before any LLM call (S4.4, design s4_4_7_tier2_design.md T-b/T-c)."""

from __future__ import annotations

from typing import Any

import pytest

from helios.pipelines.l_pipe.cache import cache_key
from helios.pipelines.l_pipe.gateway import LLMGateway
from helios.pipelines.l_pipe.ollama_client import OllamaGenerateResult
from helios.privacy.redact import (
    PII_REDACTION_ENV,
    RULESET_ID,
    luhn_ok,
    redact,
    redaction_enabled,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1In0.c2lnbmF0dXJl"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail ann.lee@example.org now", "mail <EMAIL_1> now"),
        ("from 192.168.7.21:8080", "from <IP_1>:8080"),
        ("peer 2001:db8::8a2e:370:7334 down", "peer <IP_1> down"),
        ("peer fe80:1:2:3:4:5:6:7 down", "peer <IP_1> down"),
        ("nic 3c:22:fb:1a:9e:47 up", "nic <MAC_1> up"),
        ("card 4111 1111 1111 1111 ok", "card <CARD_1> ok"),
        ("call +44 20 7946 0958 now", "call <PHONE_1> now"),
        (f"auth {JWT}", "auth <JWT_1>"),
        ("Authorization: Bearer abcDEF123456789", "Authorization: Bearer <TOKEN_1>"),
        ("password=hunter22 user=bob", "password=<SECRET_1> user=bob"),
        ("api_key: sk_live_abcdef", "api_key: <SECRET_1>"),
        # AWS's public documentation example key, not a credential.
        ("key AKIAIOSFODNN7EXAMPLE used", "key <AWS_KEY_1> used"),  # gitleaks:allow
    ],
)
def test_each_rule(text: str, expected: str) -> None:
    assert redact(text).text == expected


@pytest.mark.parametrize(
    "text",
    [
        "at 12:30:45 latency rose",  # a clock, not IPv6
        "version 1.2.3 deployed",  # three parts, not an IPv4
        "trace 4bf92f3577b34da6a3ce929d0e0e4736",  # trace ids are not PII
        "id 1234567812345678",  # fails Luhn
        "id 9111111111111111",  # no card-scheme prefix
        "checkout errors 503 on cart",
        "user=bob ok",
    ],
)
def test_near_misses_are_left_alone(text: str) -> None:
    result = redact(text)
    assert result.text == text
    assert result.counts == {}


def test_placeholders_are_numbered_by_first_appearance() -> None:
    result = redact("a@x.io b@y.io a@x.io from 10.12.3.4")
    assert result.text == "<EMAIL_1> <EMAIL_2> <EMAIL_1> from <IP_1>"
    assert result.counts == {"EMAIL": 3, "IP": 1}


def test_protected_terms_are_kept() -> None:
    assert (
        redact("svc ops@team.io", protected={"ops@team.io"}).text == "svc ops@team.io"
    )


def test_luhn() -> None:
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")


def test_setting() -> None:
    assert redaction_enabled({}) is False
    assert redaction_enabled({PII_REDACTION_ENV: "ON"}) is True
    with pytest.raises(ValueError, match="on or off"):
        redaction_enabled({PII_REDACTION_ENV: "yes"})


def test_cache_keys_are_unchanged_when_off_and_namespaced_when_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PII_REDACTION_ENV, raising=False)
    off = cache_key("m", "p", "prompt")
    # The pre-S4.4 formula, so the evidence cache stays valid.
    import hashlib

    assert off == hashlib.sha256(b"m\x00p\x00prompt").hexdigest()
    monkeypatch.setenv(PII_REDACTION_ENV, "on")
    on = cache_key("m", "p", "prompt")
    assert on != off
    assert (
        on
        == hashlib.sha256(f"m\x00p\x00prompt\x00pii:{RULESET_ID}".encode()).hexdigest()
    )


class _Client:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str, **_kw: Any) -> OllamaGenerateResult:
        self.prompts.append(prompt)
        return OllamaGenerateResult("{}", 3, 2, 7)


def test_the_gateway_redacts_before_the_model_sees_the_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(PII_REDACTION_ENV, "on")
    client = _Client()
    gateway = LLMGateway(client)  # type: ignore[arg-type]
    gateway.generate("user ann@example.org at 10.12.3.4", timeout_s=5)
    assert client.prompts == ["user <EMAIL_1> at <IP_1>"]
    assert gateway.redacting
    assert dict(gateway.redactions) == {"EMAIL": 1, "IP": 1}


def test_the_gateway_passes_prompts_through_when_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(PII_REDACTION_ENV, raising=False)
    client = _Client()
    gateway = LLMGateway(client)  # type: ignore[arg-type]
    gateway.generate("user ann@example.org", timeout_s=5)
    assert client.prompts == ["user ann@example.org"]
    assert not gateway.redacting
