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
from helios.labelling.annotations import ANNOTATIONS_ENV_VAR
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
    make(tmp_path)  # writes the set
    people_file = tmp_path / "people.json"
    people_file.write_text(json.dumps(people()), "utf-8")
    pub = tmp_path / "ann.pub.pem"
    private = generate_private_key()
    pub.write_bytes(public_key_pem(private))
    monkeypatch.setenv("DEVIATION_HMAC_SECRET", "k" * 40)
    monkeypatch.setenv(
        "DEVIATION_ED25519_PRIVATE_KEY",
        private_key_to_env_value(generate_private_key()),
    )
    monkeypatch.delenv(ANNOTATIONS_ENV_VAR, raising=False)
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
    ]
    assert tool.main(args) == 2 and started == []
    monkeypatch.setenv(
        ANNOTATIONS_ENV_VAR, private_key_to_env_value(generate_private_key())
    )
    assert tool.main(args) == 2 and started == []  # does not match the public key
    monkeypatch.setenv(ANNOTATIONS_ENV_VAR, private_key_to_env_value(private))
    assert tool.main([*args, "--port", "0"]) == 0 and len(started) == 1
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
    assert ANNOTATIONS_ENV_VAR + "=" in capsys.readouterr().out and pub.exists()
    assert tool.main(["keygen", "--public-key", str(pub)]) == 2  # never replaces a key
