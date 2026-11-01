"""bin/label_server.py (S2.9 design §5.4, R-h, R-n): loopback only, a key per
person, the annotations key and never the deviation key."""

from __future__ import annotations

import ipaddress
import json
import threading
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

import pytest

from bin import label_server as tool
from helios.labelling.annotations import (
    ANNOTATIONS_ENV_VAR,
    ANNOTATIONS_HMAC_ENV_VAR,
)
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import (
    generate_private_key,
    private_key_to_env_value,
    public_key_pem,
)
from tests.labelling.test_session import PEOPLE_KEYS, make, people

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture()
def server(tmp_path: Path) -> Iterator[tuple[str, Any]]:
    session = make(tmp_path)
    httpd = tool.make_server(session, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = str(httpd.server_address[0]), int(httpd.server_address[1])
    yield f"http://{host}:{port}", session
    httpd.shutdown()
    httpd.server_close()


def _call(base: str, path: str, key: str | None, body: Any = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        base + path, data=data, method="POST" if body else "GET"
    )
    if key is not None:
        req.add_header("X-Label-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            return resp.status, (
                json.loads(raw) if raw.startswith(b"{") or raw == b"null" else raw
            )
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def test_server_binds_loopback_only(server: tuple[str, Any]) -> None:
    base, _ = server
    host = base.split("//")[1].rsplit(":", 1)[0]
    assert ipaddress.ip_address(host).is_loopback


def test_bad_or_missing_key_gets_404(server: tuple[str, Any]) -> None:
    base, _ = server
    assert _call(base, "/api/next", None) == (404, b"")
    assert _call(base, "/api/next", "wrong") == (404, b"")
    assert _call(base, "/api/secret", PEOPLE_KEYS["R1"]) == (404, b"")


def test_page_and_api_round_trip(server: tuple[str, Any]) -> None:
    base, session = server
    status, page = _call(base, "/", None)
    assert status == 200 and b"Supported" in page and b"Unsupported" in page
    assert b'id="bcards"' in page and b'id="bheader"' in page  # review C2
    status, item = _call(base, "/api/next", PEOPLE_KEYS["R1"])
    assert status == 200 and set(item) >= {"item", "sentence", "cards"}
    status, _ = _call(
        base,
        "/api/label",
        PEOPLE_KEYS["R1"],
        {"item": item["item"], "verdict": "supported", "category": "", "note": ""},
    )
    assert status == 200
    lines = session.ledger._path.read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["person"] == "R1"
    status, _ = _call(
        base,
        "/api/label",
        PEOPLE_KEYS["R1"],
        {"item": item["item"], "verdict": "maybe", "category": "", "note": ""},
    )
    assert status == 400


def test_server_needs_the_annotations_key_not_the_deviation_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review I1: the server holds its own secrets only; any DEVIATION_* secret
    # in its environment stops it (they also sign other ledgers and seals).
    make(tmp_path)  # writes the set
    people_file = tmp_path / "people.json"
    people_file.write_text(json.dumps(people()), "utf-8")
    pub = tmp_path / "ann.pub.pem"
    private = generate_private_key()
    pub.write_bytes(public_key_pem(private))
    started: list[Any] = []
    monkeypatch.setattr(tool, "run_forever", lambda httpd: started.append(httpd))
    args = [
        "serve",
        "--set",
        str(tmp_path / "set"),
        "--people",
        str(people_file),
        "--public-key",
        str(pub),
        "--port",
        "0",
    ]
    monkeypatch.setenv(ANNOTATIONS_HMAC_ENV_VAR, "h" * 40)
    monkeypatch.setenv(ANNOTATIONS_ENV_VAR, private_key_to_env_value(private))
    for name in ("DEVIATION_HMAC_SECRET", "DEVIATION_ED25519_PRIVATE_KEY"):
        monkeypatch.setenv(name, "x" * 40)
        assert tool.main(args) == 2 and started == []
        monkeypatch.delenv(name)
    monkeypatch.delenv(ANNOTATIONS_HMAC_ENV_VAR)
    assert tool.main(args) == 2 and started == []  # no annotations HMAC secret
    monkeypatch.setenv(ANNOTATIONS_HMAC_ENV_VAR, "h" * 40)
    monkeypatch.setenv(
        ANNOTATIONS_ENV_VAR, private_key_to_env_value(generate_private_key())
    )
    assert tool.main(args) == 2 and started == []  # does not match the public key
    monkeypatch.setenv(ANNOTATIONS_ENV_VAR, private_key_to_env_value(private))
    assert tool.main(args) == 0 and len(started) == 1
    started[0].server_close()


def test_add_person_and_keygen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    people_file = tmp_path / "people.json"
    assert (
        tool.main(["add-person", "R1", "--role", "rater", "--people", str(people_file)])
        == 0
    )
    out = capsys.readouterr().out
    key = out.strip().split()[-1]
    stored = json.loads(people_file.read_text("utf-8"))
    assert stored["R1"]["role"] == "rater" and key not in people_file.read_text("utf-8")
    from helios.labelling.session import LabellingSession

    assert LabellingSession.check_key(stored, key) == "R1"
    assert (
        tool.main(["add-person", "R1", "--role", "rater", "--people", str(people_file)])
        == 2
    )
    pub = tmp_path / "keys" / "ann.pub.pem"
    assert tool.main(["keygen", "--public-key", str(pub)]) == 0
    printed = capsys.readouterr().out
    assert ANNOTATIONS_ENV_VAR + "=" in printed and pub.exists()
    assert ANNOTATIONS_HMAC_ENV_VAR + "=" in printed
    assert tool.main(["keygen", "--public-key", str(pub)]) == 2  # never replaces a key


def test_ledger_error_is_a_json_500(
    server: tuple[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review I2: a ledger failure must answer, not drop the connection.
    from helios.vcl.hmac_chain import TamperDetectedError

    base, session = server

    def boom(*_a: Any, **_k: Any) -> None:
        raise TamperDetectedError("anchor mismatch")

    monkeypatch.setattr(session, "submit", boom)
    status, body = _call(
        base,
        "/api/label",
        PEOPLE_KEYS["R1"],
        {"item": "x", "verdict": "supported", "category": "", "note": ""},
    )
    assert status == 500 and b"ledger" in body


def test_second_server_on_one_set_is_refused(tmp_path: Path) -> None:
    # Review I3: two writers would fork the ledger's chain.
    import fcntl

    make(tmp_path)
    with (tmp_path / "set" / ".serve.lock").open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert tool.acquire_set_lock(tmp_path / "set") is None
    lock = tool.acquire_set_lock(tmp_path / "set")
    assert lock is not None
    lock.close()


def test_reopen_command_reopens_a_window_of_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Review I5: the owner reopens a sitting below the floor for relabelling.
    from helios.labelling.annotations import history
    from tests.labelling.test_session import KEY, SIGNER

    session = make(tmp_path)
    for _ in range(3):
        item = session.next_item("R1")
        assert item is not None
        session.submit("R1", item["item"], "supported", "", "")
    stamps = [e["timestamp_utc"] for e in history(session.ledger, ("label",))]
    pub = tmp_path / "ann.pub.pem"
    pub.write_bytes(public_key_pem(SIGNER))
    for name in ("DEVIATION_HMAC_SECRET", "DEVIATION_ED25519_PRIVATE_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(ANNOTATIONS_HMAC_ENV_VAR, KEY.decode())
    monkeypatch.setenv(ANNOTATIONS_ENV_VAR, private_key_to_env_value(SIGNER))
    args = ["reopen", "--set", str(tmp_path / "set"), "--person", "R1"]
    args += ["--from", stamps[0], "--to", stamps[1], "--public-key", str(pub)]
    assert tool.main(args) == 0
    assert "reopened 2" in capsys.readouterr().out
    assert len(history(session.ledger, ("reopen",))) == 2
