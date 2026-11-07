"""Reward ledger: provisional and terminal rewards of the S3.3 replay (entry 74).

Ch3 Algorithm 1's two-stage reward record. One HMAC-chained file per replay
stream with an Ed25519-signed anchor (like the CoE ledger). The repo's
``reconciliation_ledger`` records run outcomes and is a different log (S3.3
design W-g).

Every learner update goes through :meth:`RewardLedger.record`, which refuses a
second record for the same (variant, stream, case, arm, stage): a redelivered
reward is never applied twice (the idempotent compensating update).
:func:`check_pairs` reads a file and checks the pairing rules:
- no duplicate (variant, stream, case, arm, stage);
- a terminal record names the provisional reward it corrects, and that is the
  earlier provisional record's reward (or null when there was none);
- no provisional record after its terminal one;
- no terminal record in a ledger with ``reconcile_terminal`` off.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.hmac_chain import HMACChainedLog

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "PROVISIONAL",
    "TERMINAL",
    "DuplicateRewardError",
    "RewardLedger",
    "check_pairs",
]

HELIOS_ENABLE_REWARD_LEDGER: bool = True

PROVISIONAL = "provisional"
TERMINAL = "terminal"


class DuplicateRewardError(RuntimeError):
    """The reward was already recorded; it must not be applied again."""


def _key(fields: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(fields[k]) for k in ("variant", "stream", "case_id", "arm", "stage")
    )


class RewardLedger(HMACChainedLog):
    """Append-only reward log of one replay stream."""

    REQUIRED_FIELDS: tuple[str, ...] = (
        "variant",
        "stream",
        "case_id",
        "arm",
        "stage",
    )
    LOG_KIND = "reward"
    ANCHOR_ED25519 = True

    _seen: set[tuple[str, ...]] | None = None

    def _seen_keys(self) -> set[tuple[str, ...]]:
        if self._seen is None:
            self._seen = set()
            if self._path.exists():
                for line in self._path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        self._seen.add(_key(json.loads(line)))
        return self._seen

    def record(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Append one reward; raise DuplicateRewardError if already recorded."""
        key = _key(fields)
        seen = self._seen_keys()
        if key in seen:
            raise DuplicateRewardError(f"reward already recorded: {key}")
        entry = self.append(fields)
        seen.add(key)
        return entry


def check_pairs(path: Path) -> str | None:
    """The first pairing-rule violation in a reward ledger, or None."""
    seen: set[tuple[str, ...]] = set()
    provisional: dict[tuple[str, ...], float] = {}
    closed: set[tuple[str, ...]] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        key = _key(entry)
        if key in seen:
            return f"line {lineno}: duplicate {entry['stage']} record"
        seen.add(key)
        pair = key[:-1]
        if entry["stage"] == PROVISIONAL:
            if pair in closed:
                return f"line {lineno}: provisional record after its terminal one"
            provisional[pair] = entry["reward"]
        elif entry["stage"] == TERMINAL:
            if not entry.get("reconcile_terminal"):
                return f"line {lineno}: terminal record with reconcile_terminal off"
            if entry.get("provisional_reward") != provisional.get(pair):
                return f"line {lineno}: terminal record names another provisional"
            closed.add(pair)
        else:
            return f"line {lineno}: unknown stage {entry['stage']!r}"
    return None
