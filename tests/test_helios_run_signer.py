"""bin/helios_run.py loads the CoE signer from the environment (S2.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from bin import helios_run as cli
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import (
    generate_private_key,
    private_key_to_env_value,
    public_key_pem,
)

if TYPE_CHECKING:
    from pathlib import Path

ENV = "DEVIATION_ED25519_PRIVATE_KEY"


def test_unset_key_gives_no_signer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV, raising=False)
    assert cli._load_coe_signer(tmp_path / "pub.pem") is None


def test_matching_key_is_loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    private = generate_private_key()
    (tmp_path / "pub.pem").write_bytes(public_key_pem(private))
    monkeypatch.setenv(ENV, private_key_to_env_value(private))
    signer = cli._load_coe_signer(tmp_path / "pub.pem")
    assert signer is not None
    assert public_key_pem(signer) == public_key_pem(private)


def test_key_not_matching_the_public_key_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "pub.pem").write_bytes(public_key_pem(generate_private_key()))
    monkeypatch.setenv(ENV, private_key_to_env_value(generate_private_key()))
    with pytest.raises(SystemExit) as exc:
        cli._load_coe_signer(tmp_path / "pub.pem")
    assert exc.value.code == 2


def test_malformed_key_exits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV, "not-base64!")
    with pytest.raises(SystemExit) as exc:
        cli._load_coe_signer(tmp_path / "pub.pem")
    assert exc.value.code == 2
