"""Labelling session: who sees which item, and every label recorded
(S2.9 design §5.4; owner decisions R-b, R-c, R-i, R-j, R-k, R-l).

Pure logic, no HTTP: ``bin/label_server.py`` wraps it. A rater is served the
next item they have not labelled, in their own seeded order, and may label
only the item currently served to them; they may revise their own label until
both raters have labelled that item. The adjudicator sees real claims the
raters disagree on (verdict, or category when both said unsupported), with the
two labels unattributed, in random order. Nothing from the sealed key reaches
a rater except, in onboarding mode, the answer after their label. State is
rebuilt from the annotations ledger at start, and a ledger that fails
verification stops the session.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import time
from typing import TYPE_CHECKING, Any

from helios.labelling.annotations import REOPENED, AnnotationLedger, history, latest
from helios.labelling.sets import rater_order
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

__all__ = ["BLINDING_EVERY", "LabellingSession", "SessionError"]

BLINDING_EVERY = 25  # labels between blinding-check questions (R-k)
_SHOWN = ("item", "header", "kind", "sentence", "cards")
_MS_PER_S = 1_000


class SessionError(ValueError):
    """A request the session refuses (unserved item, locked label, bad ledger)."""


class LabellingSession:
    def __init__(
        self,
        set_dir: Path,
        ledger: AnnotationLedger,
        people: Mapping[str, Mapping[str, str]],
        *,
        mode: str = "label",
        adjudicate_all: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if mode not in ("label", "onboarding"):
            raise SessionError(f"unknown mode {mode!r}")
        set_bytes = (set_dir / "set.json").read_bytes()
        self.manifest: dict[str, Any] = json.loads(
            (set_dir / "manifest.json").read_text("utf-8")
        )
        if hashlib.sha256(set_bytes).hexdigest() != self.manifest["set_sha256"]:
            raise SessionError("set.json does not match its manifest")
        self.items: list[dict[str, Any]] = json.loads(set_bytes)
        self._key: dict[str, dict[str, Any]] = json.loads(
            (set_dir / "key.json").read_text("utf-8")
        )
        self._by_id = {i["item"]: i for i in self.items}
        self.ledger = ledger
        # A ledger or an anchor means labels exist: a missing ledger beside an
        # anchor is tampering, not a fresh set (review I2).
        if ledger._path.exists() or ledger.anchor_path.exists():
            ok, msg = ledger.verify()
            if not ok:
                raise SessionError(f"annotations ledger failed verification: {msg}")
        # Answers from the key are shown only on an onboarding set (review I4).
        onboarding_set = self.manifest.get("purpose") == "onboarding"
        if (mode == "onboarding") != onboarding_set:
            raise SessionError(
                f"mode {mode!r} does not match the set: onboarding sets need mode "
                "'onboarding', and only they"
            )
        self.people = dict(people)
        self.mode = mode
        self.adjudicate_all = adjudicate_all
        self._clock = clock
        self._served: dict[str, tuple[str, float]] = {}
        self._blind: dict[str, str] = {}
        seed = int(self.manifest["seed"])
        self._order = {
            p: [self.items[i]["item"] for i in rater_order(seed, p, len(self.items))]
            for p in self.people
        }

    # -- people ---------------------------------------------------------------

    @staticmethod
    def check_key(people: Mapping[str, Mapping[str, str]], key: str) -> str | None:
        """The person whose key this is, or None."""
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        for person, info in people.items():
            if hmac.compare_digest(digest, str(info["key_sha256"])):
                return person
        return None

    def _raters(self) -> list[str]:
        return sorted(p for p, i in self.people.items() if i["role"] == "rater")

    def _role(self, person: str) -> str:
        if person not in self.people:
            raise SessionError(f"unknown person {person!r}")
        return str(self.people[person]["role"])

    # -- state ----------------------------------------------------------------

    def _labels(self) -> dict[tuple[str, str], dict[str, Any]]:
        """Each person's standing label per item; a reopen (R-m relabel)
        withdraws it until the person labels the item again."""
        state: dict[tuple[str, str], dict[str, Any] | None] = {}
        for e in history(self.ledger, ("label", "reopen")):
            pair = (str(e["item"]), str(e["person"]))
            state[pair] = e if e["kind"] == "label" else None
        return {pair: e for pair, e in state.items() if e is not None}

    def reopen(self, person: str, items: list[str]) -> int:
        """Reopen ``person``'s labels on ``items`` for relabelling (a sitting
        under the detection floor, R-m); returns how many were reopened."""
        labels = self._labels()
        n = 0
        for item in items:
            if (item, person) in labels:
                self.ledger.append(
                    {
                        "set_hash": self.manifest["set_sha256"],
                        "item": item,
                        "person": person,
                        "kind": "reopen",
                        "verdict": REOPENED,
                        "category": "",
                        "note": "",
                        "dwell_ms": 0,
                    }
                )
                n += 1
        return n

    def _locked(self, item: str, labels: Mapping[tuple[str, str], Any]) -> bool:
        return all((item, r) in labels for r in self._raters())

    def _queue(self) -> list[str]:
        labels = self._labels()
        done = {i for i, _ in latest(self.ledger, "adjudication")}
        r1, r2 = [*self._raters(), "", ""][:2]
        out = []
        for item in self._order[next(iter(self.people))]:
            if self._key[item]["planted"] or item in done:
                continue
            a, b = labels.get((item, r1)), labels.get((item, r2))
            if a is None or b is None:
                continue
            differ = a["verdict"] != b["verdict"] or a["category"] != b["category"]
            if self.adjudicate_all or differ:
                out.append(item)
        return out

    def _shown(self, item: str) -> dict[str, Any]:
        return {k: self._by_id[item][k] for k in _SHOWN}

    def _serve(self, person: str, item: str) -> None:
        if self._served.get(person, ("", 0))[0] != item:
            self._served[person] = (item, self._clock())

    # -- flow -----------------------------------------------------------------

    def progress(self, person: str) -> dict[str, int]:
        mine = [i for i, p in self._labels() if p == person]
        return {"labelled": len(mine), "total": len(self.items)}

    def next_item(self, person: str) -> dict[str, Any] | None:
        """The item to show next, or None when there is nothing left."""
        if self._role(person) == "adjudicator":
            queue = self._queue()
            if not queue:
                return None
            item = queue[0]
            labels = self._labels()
            pair = [
                {
                    "verdict": labels[item, r]["verdict"],
                    "category": labels[item, r]["category"],
                }
                for r in self._raters()
            ]
            random.Random(f"{self.manifest['seed']}:{item}").shuffle(pair)
            self._serve(person, item)
            return {**self._shown(item), "labels": pair}
        labels = self._labels()
        for item in self._order[person]:
            if (item, person) not in labels:
                self._serve(person, item)
                return {**self._shown(item), "progress": self.progress(person)}
        return None

    def revisit(self, person: str, item: str) -> dict[str, Any]:
        """Serve an item the rater labelled before, to revise it."""
        labels = self._labels()
        if self._role(person) != "rater" or (item, person) not in labels:
            raise SessionError("only a rater's own labelled item can be revisited")
        if self._locked(item, labels):
            raise SessionError("locked: both raters have labelled this item")
        self._serve(person, item)
        return self._shown(item)

    def submit(
        self, person: str, item: str, verdict: str, category: str, note: str
    ) -> dict[str, Any] | None:
        """Record a label (or an adjudication); in onboarding mode, return the
        answer from the key."""
        role = self._role(person)
        served = self._served.get(person)
        if served is None or served[0] != item:
            raise SessionError("item not served to this person")
        labels = self._labels()
        if role == "rater" and (item, person) in labels and self._locked(item, labels):
            raise SessionError("locked: both raters have labelled this item")
        dwell = int((self._clock() - served[1]) * _MS_PER_S)
        self.ledger.append(
            {
                "set_hash": self.manifest["set_sha256"],
                "item": item,
                "person": person,
                "kind": "adjudication" if role == "adjudicator" else "label",
                "verdict": verdict,
                "category": category,
                "note": note[:200],
                "dwell_ms": max(dwell, 0),
            }
        )
        del self._served[person]
        if self.mode == "onboarding":
            k = self._key[item]
            return {"planted": k["planted"], "category": k["category"]}
        return None

    def blinding_prompt(self, person: str) -> dict[str, Any] | None:
        """After every BLINDING_EVERY labels, one labelled real claim to ask
        "language model, fixed rules, or can't tell?" about (R-k)."""
        if self._role(person) != "rater":
            return None
        labels = self._labels()
        mine = [i for i, p in labels if p == person]
        guessed = {i for i, p in latest(self.ledger, "blind_guess") if p == person}
        due = len(mine) // BLINDING_EVERY
        if due <= len(guessed):
            return None
        if person not in self._blind:
            pool = sorted(
                i for i in mine if not self._key[i]["planted"] and i not in guessed
            )
            if not pool:
                return None
            rng = random.Random(f"{self.manifest['seed']}:{person}:{len(guessed)}")
            self._blind[person] = rng.choice(pool)
        return self._shown(self._blind[person])

    def submit_guess(self, person: str, item: str, guess: str) -> None:
        if self._blind.get(person) != item:
            raise SessionError("no blinding question open for this item")
        self.ledger.append(
            {
                "set_hash": self.manifest["set_sha256"],
                "item": item,
                "person": person,
                "kind": "blind_guess",
                "verdict": guess,
                "category": "",
                "note": "",
                "dwell_ms": 0,
            }
        )
        del self._blind[person]
