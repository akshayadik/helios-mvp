"""Ed25519 layer on the HMAC-chained ledgers (owner decision D7, S0.9).

A test log turns on Ed25519 at entry 3, so entries 1-2 play the role of the
34 HMAC-only entries of the real deviation log.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import bin.log_deviation as cli
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import (
    generate_private_key,
    load_private_key,
    load_public_key,
    private_key_to_env_value,
    public_key_pem,
    sign_fields,
    verify_fields,
)
from helios.vcl.hmac_chain import HMACChainedLog, TamperDetectedError, verify_public

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"k" * 32
FIELDS = {"change": "c", "reason": "r"}


class _Log(HMACChainedLog):
    REQUIRED_FIELDS = ("change", "reason")
    LOG_KIND = "test"
    ED25519_FROM_ENTRY = 3


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _write_lines(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in entries))


@pytest.fixture()
def signed_log(tmp_path: Path) -> tuple[_Log, Path]:
    """A log with 2 HMAC-only entries and 2 Ed25519-signed entries."""
    path = tmp_path / "test_log.jsonl"
    private = generate_private_key()
    _Log(KEY, path).append(FIELDS)
    _Log(KEY, path).append(FIELDS)
    log = _Log(KEY, path, ed25519_private=private)
    log.append(FIELDS)
    log.append(FIELDS)
    return log, path


def _public_check(log: _Log, path: Path) -> tuple[bool, str]:
    assert log._ed_public is not None
    return verify_public(
        path, log.anchor_path, log._ed_public, from_entry=3, log_kind="test"
    )


# --- key handling -----------------------------------------------------------


def test_private_key_env_value_round_trips() -> None:
    key = generate_private_key()
    again = load_private_key(private_key_to_env_value(key))
    assert public_key_pem(again) == public_key_pem(key)


@pytest.mark.parametrize(
    ("value", "message"), [("***", "base64"), ("AAAA", "32 bytes")]
)
def test_malformed_private_key_is_refused(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_private_key(value)


def test_public_key_file_must_be_ed25519(tmp_path: Path) -> None:
    ec_pem = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    path = tmp_path / "ec.pem"
    path.write_bytes(ec_pem)
    with pytest.raises(ValueError, match="not an Ed25519"):
        load_public_key(path)


def test_signatures_are_deterministic_and_reject_bad_hex() -> None:
    key = generate_private_key()
    assert sign_fields(key, FIELDS) == sign_fields(key, FIELDS)
    assert not verify_fields(key.public_key(), FIELDS, "zz")


# --- chain with the Ed25519 layer ------------------------------------------


def test_signed_log_verifies_with_secret_and_with_public_key(
    signed_log: tuple[_Log, Path],
) -> None:
    log, path = signed_log
    entries = _lines(path)
    assert [("ed25519_signature" in e) for e in entries] == [False, False, True, True]
    assert log.verify() == (True, "Chain verified.")
    ok, msg = _public_check(log, path)
    assert ok, msg
    assert "4 entries (2 Ed25519-signed" in msg


def test_hmac_signatures_of_old_entries_are_unchanged(tmp_path: Path) -> None:
    plain, signed = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    _Log(KEY, plain).append(FIELDS)
    _Log(KEY, signed, ed25519_private=generate_private_key()).append(FIELDS)
    assert "ed25519_signature" not in _lines(signed)[0]


def test_append_in_signed_era_needs_the_private_key(
    signed_log: tuple[_Log, Path],
) -> None:
    _, path = signed_log
    with pytest.raises(ValueError, match="must be Ed25519-signed"):
        _Log(KEY, path).append(FIELDS)


def test_verify_without_public_key_fails_in_signed_era(
    signed_log: tuple[_Log, Path],
) -> None:
    _, path = signed_log
    ok, msg = _Log(KEY, path).verify()
    assert not ok
    assert "public key required" in msg


def test_stripped_entry_signature_is_detected(signed_log: tuple[_Log, Path]) -> None:
    log, path = signed_log
    entries = _lines(path)
    del entries[3]["ed25519_signature"]
    _write_lines(path, entries)
    assert not log.verify()[0]
    assert not _public_check(log, path)[0]


def test_signature_before_the_boundary_is_rejected(
    signed_log: tuple[_Log, Path],
) -> None:
    log, path = signed_log
    entries = _lines(path)
    entries[0]["ed25519_signature"] = entries[2]["ed25519_signature"]
    _write_lines(path, entries)
    ok, msg = log.verify()
    assert not ok
    assert "before the boundary" in msg


def test_wrong_public_key_fails(signed_log: tuple[_Log, Path]) -> None:
    _, path = signed_log
    other = generate_private_key().public_key()
    log = _Log(KEY, path, ed25519_public=other)
    assert not log.verify()[0]
    assert not verify_public(
        path, log.anchor_path, other, from_entry=3, log_kind="test"
    )[0]


def test_edit_to_an_hmac_only_entry_fails_the_public_check(
    signed_log: tuple[_Log, Path],
) -> None:
    log, path = signed_log
    path.write_text(path.read_text().replace('"change": "c"', '"change": "X"', 1))
    ok, msg = _public_check(log, path)
    assert not ok
    assert "digest" in msg


def test_hmac_key_holder_cannot_rewrite_history(signed_log: tuple[_Log, Path]) -> None:
    """Re-signing the whole HMAC chain and anchor still fails without the Ed25519 key."""
    log, path = signed_log
    entries = _lines(path)
    entries[0]["change"] = "rewritten"
    prev = "GENESIS"
    for e in entries:
        e["prev_signature"] = prev
        e["signature"] = log.compute_signature(e)
        prev = e["signature"]
    _write_lines(path, entries)
    anchor = json.loads(log.anchor_path.read_text())
    fields = log._anchor_fields(len(entries), prev)
    anchor.update(fields, anchor_signature=log._sign(fields))
    log.anchor_path.write_text(json.dumps(anchor))
    assert not log.verify()[0]
    assert not _public_check(log, path)[0]


def test_truncation_is_detected_by_the_public_check(
    signed_log: tuple[_Log, Path],
) -> None:
    log, path = signed_log
    _write_lines(path, _lines(path)[:-1])
    assert not _public_check(log, path)[0]


def test_forged_anchor_digest_fails(signed_log: tuple[_Log, Path]) -> None:
    log, path = signed_log
    anchor = json.loads(log.anchor_path.read_text())
    anchor["log_sha256"] = "0" * 64
    log.anchor_path.write_text(json.dumps(anchor))
    ok, msg = log.verify()
    assert not ok
    assert "log_sha256" in msg
    assert not _public_check(log, path)[0]


def test_anchor_without_ed25519_signature_fails(signed_log: tuple[_Log, Path]) -> None:
    log, path = signed_log
    anchor = json.loads(log.anchor_path.read_text())
    del anchor["anchor_ed25519_signature"]
    log.anchor_path.write_text(json.dumps(anchor))
    assert "lacks its Ed25519" in log.verify()[1]
    assert "no Ed25519" in _public_check(log, path)[1]


def test_public_check_refusals(tmp_path: Path, signed_log: tuple[_Log, Path]) -> None:
    log, path = signed_log
    pub = log._ed_public
    assert pub is not None
    missing = verify_public(
        path, tmp_path / "none.json", pub, from_entry=3, log_kind="test"
    )
    assert "missing" in missing[1]
    wrong_kind = verify_public(
        path, log.anchor_path, pub, from_entry=3, log_kind="deviation"
    )
    assert "log kind" in wrong_kind[1]
    early = verify_public(path, log.anchor_path, pub, from_entry=9, log_kind="test")
    assert "starts at 9" in early[1]


def test_broken_link_fails_the_public_check(signed_log: tuple[_Log, Path]) -> None:
    log, path = signed_log
    entries = _lines(path)
    entries[1]["prev_signature"] = "f" * 64
    _write_lines(path, entries)
    assert "digest" in _public_check(log, path)[1]
    # Even a key holder who re-signs the anchor over a malformed log is caught.
    log._write_anchor(len(entries), entries[-1]["signature"])
    assert "link broken" in _public_check(log, path)[1]
    assert not log.verify()[0]


def test_anchoring_in_signed_era_needs_private_key(
    signed_log: tuple[_Log, Path],
) -> None:
    signer, path = signed_log
    log = _Log(KEY, path, ed25519_public=signer._ed_public)
    log.anchor_path.unlink()
    with pytest.raises(ValueError, match="private key required"):
        log.init_anchor()


def test_tampered_log_refuses_append(signed_log: tuple[_Log, Path]) -> None:
    log, path = signed_log
    _write_lines(path, _lines(path)[:-1])
    with pytest.raises(TamperDetectedError):
        log.append(FIELDS)


# --- CLI ----------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", "s" * 40)
    monkeypatch.delenv("DEVIATION_ED25519_PRIVATE_KEY", raising=False)
    monkeypatch.setattr(cli, "ED25519_FROM_ENTRY", 2)
    monkeypatch.setattr(cli.DeviationLog, "ED25519_FROM_ENTRY", 2)
    return tmp_path


def _append_args(n: int) -> list[str]:
    return [
        "--stage",
        "S",
        "--clause",
        f"§{n}",
        "--change",
        "c",
        "--reason",
        "r",
        "--analytic-consequence",
        "a",
    ]


def test_cli_keygen_append_and_both_verifications(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["keygen"]) == 0
    env_line = capsys.readouterr().out.strip()
    name, value = env_line.split("=", 1)
    assert name == "DEVIATION_ED25519_PRIVATE_KEY"
    assert (repo / cli.PUBLIC_KEY_FILE).exists()
    assert cli.main(["keygen"]) == 2  # never replaces the committed public key

    monkeypatch.setenv(name, value)
    assert cli.main(_append_args(1)) == 0
    assert cli.main(_append_args(2)) == 0
    assert cli.main(["verify"]) == 0
    assert cli.main(["verify-public"]) == 0
    assert "2 entries (1 Ed25519-signed" in capsys.readouterr().out


def test_cli_append_needs_matching_private_key(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["keygen"]) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as missing:
        cli.main(_append_args(1))
    assert missing.value.code == 2
    monkeypatch.setenv(
        "DEVIATION_ED25519_PRIVATE_KEY",
        private_key_to_env_value(generate_private_key()),
    )
    with pytest.raises(SystemExit) as mismatch:
        cli.main(_append_args(1))
    assert mismatch.value.code == 2
    monkeypatch.setenv("DEVIATION_ED25519_PRIVATE_KEY", "AAAA")
    with pytest.raises(SystemExit) as malformed:
        cli.main(_append_args(1))
    assert malformed.value.code == 2
    assert "does not match" in capsys.readouterr().err


def test_cli_verify_public_without_key_file(repo: Path) -> None:
    assert cli.main(["verify-public"]) == 1
