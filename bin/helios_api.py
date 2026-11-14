#!/usr/bin/env python3
"""Serve the HELIOS API over one campaign (S4.1; design s4_1_api_design.md).

Usage (from the repository root):
    poetry run python bin/helios_api.py secret >> .env.api        # once; chmod 600
    poetry run python bin/helios_api.py keygen --keys api_keys.json --id R1 --role reviewer
    env -i PATH="$PATH" HOME="$HOME" sh -c 'set -a; . ./.env.api; set +a; \\
        poetry run python bin/helios_api.py serve --campaign CAMPAIGN --keys api_keys.json'
    poetry run python bin/helios_api.py export-spec               # docs/api/openapi.json

The server reads only the decisions secret (``HELIOS_DECISIONS_HMAC_SECRET``)
and refuses to start if any ``DEVIATION_*`` variable is in its environment:
CoE ledgers are verified with the committed public key alone. It binds to the
loopback interface (``localhost``) unless ``--host`` says otherwise. A key is
printed once by ``keygen`` and only its SHA-256 digest is stored.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.api import API_VERSION
from helios.api.app import ApiConfig, create_app
from helios.api.auth import ROLES, add_key
from helios.api.decisions import DECISIONS_SECRET_ENV
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_KEY = REPO_ROOT / "keys" / "deviation_log_ed25519.pub.pem"
SPEC_PATH = REPO_ROOT / "docs" / "api" / "openapi.json"
LOOPBACK = "localhost"
DEFAULT_PORT = 8080
_SECRET_BYTES = 32


def refuse_deviation_env(environ: dict[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    leaked = sorted(k for k in env if k.startswith("DEVIATION_"))
    if leaked:
        raise SystemExit(
            f"refused: {', '.join(leaked)} in the environment; the API never "
            "holds the deviation-log secrets (start it with env -i)"
        )


def decisions_secret(environ: dict[str, str] | None = None) -> bytes:
    env = os.environ if environ is None else environ
    raw = env.get(DECISIONS_SECRET_ENV, "")
    if len(raw) < _SECRET_BYTES:
        raise SystemExit(f"{DECISIONS_SECRET_ENV} is missing or shorter than 32 bytes")
    return raw.encode()


def config_for(campaign: Path, keys: Path, secret: bytes) -> ApiConfig:
    """A campaign directory's store, CoE ledgers and decisions ledger."""
    return ApiConfig(
        store_path=campaign / "results.duckdb",
        coe_dir=campaign / "coe",
        decisions_path=campaign / "decisions" / "decisions.jsonl",
        keys_path=keys,
        decisions_secret=secret,
        public_key_path=PUBLIC_KEY,
    )


def spec_text(tmp: Path) -> str:
    """The committed form of the OpenAPI spec, from an app over an empty
    store (the spec does not depend on the data)."""
    import duckdb

    store = tmp / "empty.duckdb"
    con = duckdb.connect(str(store))
    con.execute((REPO_ROOT / "helios/store/schema.sql").read_text())
    con.close()
    app = create_app(
        ApiConfig(
            store_path=store,
            coe_dir=None,
            decisions_path=tmp / "decisions.jsonl",
            keys_path=tmp / "keys.json",
            decisions_secret=b"s" * _SECRET_BYTES,
            public_key_path=PUBLIC_KEY,
        )
    )
    return json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--campaign", type=Path, required=True)
    serve.add_argument("--keys", type=Path, required=True)
    serve.add_argument("--host", default=LOOPBACK)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("--keys", type=Path, required=True)
    keygen.add_argument("--id", required=True)
    keygen.add_argument("--role", action="append", choices=ROLES, required=True)
    sub.add_parser("secret")
    spec = sub.add_parser("export-spec")
    spec.add_argument("--output", type=Path, default=SPEC_PATH)
    args = parser.parse_args(argv)

    if args.cmd == "secret":
        print(f"{DECISIONS_SECRET_ENV}={secrets.token_urlsafe(_SECRET_BYTES)}")
        return 0
    if args.cmd == "keygen":
        print(add_key(args.keys, args.id, list(args.role)))  # shown once
        return 0
    if args.cmd == "export-spec":
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(spec_text(Path(tmp)))
        print(f"[api] {API_VERSION} spec written to {args.output}")
        return 0
    refuse_deviation_env()  # pragma: no cover - serve starts a server
    import uvicorn  # pragma: no cover

    app = create_app(config_for(args.campaign, args.keys, decisions_secret()))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
