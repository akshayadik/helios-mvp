"""Labelling server for H_fact raters (S2.9 design §5.4; R-h, R-l, R-n).

Usage (from the repository root, on the owner's machine):
    poetry run python bin/label_server.py keygen > .env.labelling   # once; back it up
    poetry run python bin/label_server.py add-person R1 --role rater
    poetry run python bin/label_server.py add-person ADJ --role adjudicator
    env -i PATH="$PATH" HOME="$HOME" sh -c 'set -a; . ./.env.labelling; set +a; \
        poetry run python bin/label_server.py serve --set data/labelling/training-1'

The server reads only its own secrets (``.env.labelling``: the annotations
HMAC secret and Ed25519 key) and refuses to start if any ``DEVIATION_*``
variable is in its environment (review I1).

Listens on the loopback interface only; raters reach it through the owner's
tunnel and open ``/#key=<their key>`` (the key stays in the URL fragment, so
it never reaches the server log or a proxy). Every label is appended to the
set's annotations ledger, signed with the annotations key (never the
deviation-log key).
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import ipaddress
import json
import secrets
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bin.log_deviation import load_public_key_file
from helios.labelling.annotations import (
    ANNOTATIONS_ENV_VAR,
    ANNOTATIONS_HMAC_ENV_VAR,
    ANNOTATIONS_PUBLIC_KEY_FILE,
    AnnotationLedger,
    history,
    load_annotations_hmac,
)
from helios.labelling.session import LabellingSession, SessionError
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.ed25519 import (
    generate_private_key,
    load_private_key,
    private_key_to_env_value,
    public_key_pem,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["acquire_set_lock", "main", "make_server", "run_forever"]

LOOPBACK = str(ipaddress.IPv4Address(socket.INADDR_LOOPBACK))
DEFAULT_PORT = 8765
DEFAULT_PEOPLE = Path("data/labelling/people.json")
PAGE = Path(__file__).resolve().parent.parent / "helios/labelling/page.html"
_MAX_BODY = 8_192


def _handler(session: LabellingSession) -> type[BaseHTTPRequestHandler]:
    lock = threading.Lock()
    page = PAGE.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            del format, args  # quiet: no paths or keys in the console

        def _send(
            self, status: int, body: bytes = b"", kind: str = "application/json"
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: Any, status: int = 200) -> None:
            self._send(status, json.dumps(obj).encode("utf-8"))

        def _person(self) -> str | None:
            return LabellingSession.check_key(
                session.people, self.headers.get("X-Label-Key", "")
            )

        def do_GET(self) -> None:  # noqa: N802 — http.server API name
            if self.path == "/":
                self._send(200, page, "text/html; charset=utf-8")
                return
            person = self._person()
            routes: dict[str, Callable[[str], Any]] = {
                "/api/next": session.next_item,
                "/api/blind": session.blinding_prompt,
                "/api/progress": session.progress,
            }
            if person is None or self.path not in routes:
                self._send(404)
                return
            with lock:
                self._json(routes[self.path](person))

        def do_POST(self) -> None:  # noqa: N802 — http.server API name
            person = self._person()
            length = int(self.headers.get("Content-Length", "0") or 0)
            if person is None or not 0 < length <= _MAX_BODY:
                self._send(404)
                return
            try:
                body = json.loads(self.rfile.read(length))
                with lock:
                    if self.path == "/api/label":
                        answer = session.submit(
                            person,
                            str(body["item"]),
                            str(body["verdict"]),
                            str(body.get("category", "")),
                            str(body.get("note", "")),
                        )
                        self._json({"ok": True, "answer": answer})
                    elif self.path == "/api/blind":
                        session.submit_guess(
                            person, str(body["item"]), str(body["guess"])
                        )
                        self._json({"ok": True})
                    elif self.path == "/api/revisit":
                        self._json(session.revisit(person, str(body["item"])))
                    else:
                        self._send(404)
            except (SessionError, ValueError, KeyError, TypeError) as exc:
                self._json({"error": str(exc)}, status=400)
            except (RuntimeError, OSError) as exc:  # ledger tampering, disk (review I2)
                self._json({"error": f"ledger or storage error: {exc}"}, status=500)

    return Handler


def make_server(
    session: LabellingSession, *, port: int = DEFAULT_PORT
) -> ThreadingHTTPServer:
    """The HTTP server for ``session``, bound to the loopback interface only."""
    return ThreadingHTTPServer((LOOPBACK, port), _handler(session))


def acquire_set_lock(set_dir: Path) -> IO[str] | None:
    """An exclusive lock on the set for this process, or None if another
    server holds it: two writers would fork the ledger's chain (review I3)."""
    handle = (set_dir / ".serve.lock").open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def run_forever(httpd: ThreadingHTTPServer) -> None:
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def _ledger(args: argparse.Namespace) -> AnnotationLedger | str:
    """The set's annotations ledger with the server's own keys, or why not."""
    import os

    leaked = sorted(k for k in os.environ if k.startswith("DEVIATION_"))
    if leaked:
        return f"deviation secrets in the environment: {leaked}"
    hmac_key = load_annotations_hmac()
    if hmac_key is None:
        return f"needs {ANNOTATIONS_HMAC_ENV_VAR}"
    public = load_public_key_file(args.public_key)
    value = os.getenv(ANNOTATIONS_ENV_VAR)
    if public is None or not value:
        return f"needs {ANNOTATIONS_ENV_VAR} and {args.public_key}"
    private = load_private_key(value)
    if public_key_pem(private) != args.public_key.read_bytes():
        return "the annotations key does not match its public key"
    return AnnotationLedger(
        hmac_key,
        args.set / f"{args.set.name}.annotations.jsonl",
        ed25519_private=private,
    )


def _session(
    args: argparse.Namespace, people: dict[str, Any], **kw: Any
) -> LabellingSession | str:
    ledger = _ledger(args)
    if isinstance(ledger, str):
        return ledger
    try:
        return LabellingSession(args.set, ledger, people, **kw)
    except SessionError as exc:
        return str(exc)


def _refused(why: str) -> int:
    print(f"[label] refused: {why}", file=sys.stderr)
    return 2


def _serve(args: argparse.Namespace) -> int:
    people = json.loads(args.people.read_text("utf-8"))
    lock = acquire_set_lock(args.set)
    if lock is None:
        return _refused("another server is using this set")
    try:
        session = _session(
            args, people, mode=args.mode, adjudicate_all=args.adjudicate_all
        )
        if isinstance(session, str):
            return _refused(session)
        httpd = make_server(session, port=args.port)
        port = httpd.server_address[1]
        print(f"[label] serving on {LOOPBACK}:{port} ({len(session.items)} items)")
        run_forever(httpd)
        return 0
    finally:
        lock.close()


def _reopen(args: argparse.Namespace) -> int:
    """Reopen one person's labels given between two server timestamps, for
    relabelling a sitting under the detection floor (R-m, review I5)."""
    manifest = json.loads((args.set / "manifest.json").read_text("utf-8"))
    mode = "onboarding" if manifest.get("purpose") == "onboarding" else "label"
    people = {args.person: {"key_sha256": "", "role": "rater"}}
    lock = acquire_set_lock(args.set)
    if lock is None:
        return _refused("stop the server first")
    try:
        session = _session(args, people, mode=mode)
        if isinstance(session, str):
            return _refused(session)
        items = sorted(
            {
                str(e["item"])
                for e in history(session.ledger, ("label",))
                if e["person"] == args.person
                and args.start <= str(e["timestamp_utc"]) <= args.end
            }
        )
        n = session.reopen(args.person, items)
        print(f"[label] reopened {n} labels of {args.person}")
        return 0
    finally:
        lock.close()


def _add_person(args: argparse.Namespace) -> int:
    people = json.loads(args.people.read_text("utf-8")) if args.people.exists() else {}
    if args.name in people:
        print(f"[label] {args.name} already exists", file=sys.stderr)
        return 2
    key = secrets.token_urlsafe(24)
    people[args.name] = {
        "key_sha256": hashlib.sha256(key.encode("utf-8")).hexdigest(),
        "role": args.role,
    }
    args.people.parent.mkdir(parents=True, exist_ok=True)
    args.people.write_text(json.dumps(people, indent=1, sort_keys=True) + "\n", "utf-8")
    print(
        f"[label] {args.name} ({args.role}); open /#key=<key>; shown once, key: {key}"
    )
    return 0


def _keygen(args: argparse.Namespace) -> int:
    if args.public_key.exists():
        print(
            f"[label] refused: {args.public_key} exists; keys are never replaced",
            file=sys.stderr,
        )
        return 2
    private = generate_private_key()
    args.public_key.parent.mkdir(parents=True, exist_ok=True)
    args.public_key.write_bytes(public_key_pem(private))
    print(f"{ANNOTATIONS_HMAC_ENV_VAR}={secrets.token_urlsafe(32)}")
    print(f"{ANNOTATIONS_ENV_VAR}={private_key_to_env_value(private)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--set", type=Path, required=True)
    serve.add_argument("--people", type=Path, default=DEFAULT_PEOPLE)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--mode", choices=("label", "onboarding"), default="label")
    serve.add_argument(
        "--adjudicate-all", action="store_true", help="R-m: kappa below 0.7"
    )
    serve.add_argument("--public-key", type=Path, default=ANNOTATIONS_PUBLIC_KEY_FILE)
    add = sub.add_parser("add-person")
    add.add_argument("name")
    add.add_argument("--role", choices=("rater", "adjudicator"), required=True)
    add.add_argument("--people", type=Path, default=DEFAULT_PEOPLE)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("--public-key", type=Path, default=ANNOTATIONS_PUBLIC_KEY_FILE)
    reopen = sub.add_parser("reopen", help="R-m: relabel a sitting under the floor")
    reopen.add_argument("--set", type=Path, required=True)
    reopen.add_argument("--person", required=True)
    reopen.add_argument("--from", dest="start", required=True, help="timestamp_utc")
    reopen.add_argument("--to", dest="end", required=True, help="timestamp_utc")
    reopen.add_argument("--public-key", type=Path, default=ANNOTATIONS_PUBLIC_KEY_FILE)
    args = parser.parse_args(argv)
    return {
        "serve": _serve,
        "add-person": _add_person,
        "keygen": _keygen,
        "reopen": _reopen,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
