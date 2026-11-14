#!/usr/bin/env python3
"""Simulated HITL: a scripted reviewer that drives the real API flow (S4.2 K-f).

Usage (the API serving a campaign; the key file holds one simulated key):
    poetry run python bin/helios_api.py keygen --keys api_keys.json --id SIM1 \\
        --role reviewer --simulated > sim.key
    poetry run python bin/simulate_hitl.py --api http://localhost:8080 \\
        --key-file sim.key --policy accept [--threshold T] [--limit N]

For every run whose verdict requests a human (PROVISIONAL or NON_CONVERGED) it
opens a view and records a decision, exactly as a person at the console
would. Policies read no labels: ``accept`` (the top-ranked service),
``escalate``, or ``confidence`` (accept at or above ``--threshold``, which has
no default, otherwise escalate). Runs already decided by this key are skipped,
so a second pass resumes.

Timing: the server measures its own ``decision_ms`` (milliseconds here, since
nothing waits). The modelled think time, the price book's human review time,
is sent as ``client_ms``. Every entry is tagged ``simulated`` by the key, so
analysis never mixes these decisions with a person's. No metric changes: CpR
keeps charging the fixed human time (S4.9 M-c). Prints counts only.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helios.evaluation.cost import load_price_book
from helios.vcl.config import VCLManifest  # noqa: F401  # flag-guard compliance

POLICIES = ("accept", "escalate", "confidence")
_PAGE = 200
_MS_PER_MIN = 60_000
_HTTP_OK_MAX = 299


class Response(Protocol):
    status_code: int

    def json(self) -> Any: ...


class Client(Protocol):
    """requests.Session-like; FastAPI's TestClient fits too."""

    def get(self, url: str, **kwargs: Any) -> Response: ...

    def post(self, url: str, **kwargs: Any) -> Response: ...


@dataclass(frozen=True)
class Policy:
    name: str
    threshold: float | None = None

    def __post_init__(self) -> None:
        if self.name not in POLICIES:
            raise ValueError(f"unknown policy {self.name!r}")
        if self.name == "confidence" and self.threshold is None:
            raise ValueError("the confidence policy needs --threshold")

    def decide(self, verdict: dict[str, Any]) -> str:
        if self.name == "accept":
            return "accept"
        if self.name == "escalate":
            return "escalate"
        confidence = verdict.get("confidence")
        assert self.threshold is not None
        return (
            "accept"
            if confidence is not None and confidence >= self.threshold
            else "escalate"
        )


class ApiError(RuntimeError):
    pass


def _ok(resp: Response, what: str) -> Any:
    if resp.status_code > _HTTP_OK_MAX:
        raise ApiError(f"{what}: HTTP {resp.status_code}")
    return resp.json()


def runs_needing_review(
    client: Client, base: str, headers: dict[str, str]
) -> list[str]:
    """Every run whose verdict requests a human, in incident order."""
    runs: list[str] = []
    offset = 0
    while True:
        page = _ok(
            client.get(
                f"{base}/v1/incidents",
                headers=headers,
                params={"limit": _PAGE, "offset": offset},
            ),
            "incidents",
        )
        for item in page["items"]:
            detail = _ok(
                client.get(
                    f"{base}/v1/incidents/{item['incident_id']}", headers=headers
                ),
                "incident",
            )
            runs += [r["run_id"] for r in detail["runs"] if r["needs_review"]]
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            return runs


def already_decided(
    client: Client, base: str, headers: dict[str, str], run_id: str, key_id: str
) -> bool:
    listed = _ok(
        client.get(f"{base}/v1/verdicts/{run_id}/decisions", headers=headers),
        "decisions",
    )
    return any(d["key_id"] == key_id and d["simulated"] for d in listed["decisions"])


def simulate(
    client: Client,
    base: str,
    key: str,
    key_id: str,
    policy: Policy,
    *,
    think_ms: float,
    limit: int | None = None,
) -> Counter[str]:
    """Record one decision per human-requesting run; counts by outcome."""
    headers = {"X-API-Key": key}
    counts: Counter[str] = Counter()
    for run_id in runs_needing_review(client, base, headers)[:limit]:
        if already_decided(client, base, headers, run_id, key_id):
            counts["skipped"] += 1
            continue
        verdict = _ok(
            client.get(f"{base}/v1/verdicts/{run_id}", headers=headers), "verdict"
        )
        decision = policy.decide(verdict)
        view = _ok(
            client.post(f"{base}/v1/verdicts/{run_id}/views", headers=headers), "view"
        )
        body = {
            "decision": decision,
            "view_token": view["view_token"],
            "client_ms": think_ms,
            "note": f"simulated HITL, policy {policy.name}",
        }
        out = _ok(
            client.post(
                f"{base}/v1/verdicts/{run_id}/decisions", headers=headers, json=body
            ),
            "decision",
        )
        if not out["simulated"]:
            raise ApiError("the key is not a simulated key; refusing to continue")
        counts[decision] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", required=True, help="base URL of the API")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--key-id", required=True, help="the simulated key's ID")
    parser.add_argument("--policy", choices=POLICIES, default="accept")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    policy = Policy(args.policy, args.threshold)
    think_ms = load_price_book().human_review_minutes * _MS_PER_MIN
    import requests

    with requests.Session() as session:
        counts = simulate(
            session,  # type: ignore[arg-type]
            args.api.rstrip("/"),
            args.key_file.read_text().strip(),
            args.key_id,
            policy,
            think_ms=think_ms,
            limit=args.limit,
        )
    print(f"[simulated HITL] policy {policy.name}: {dict(sorted(counts.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
