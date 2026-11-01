"""Output schema per slot for the LLM narrator (S2.8 prompt round 2).

Round 1 showed the 8B model inventing evidence IDs, services and field
combinations (3-12% of first-draft claims passed). The schema, sent as the
model's output format, offers only the field combinations the entry supports:
the fused ranking, each D-pipe channel item with its evidence direction, each
G-pipe edge, each L-pipe log line, each disagreeing pipeline's top suspect,
read-only steps on the top 3. The model still chooses which claims to make and
writes every sentence and snippet; the verifier still checks each claim on its
own (the schema is a guide to the model, not a gate).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from helios.narrative.claims import Claim, ClaimKind
from helios.narrative.prompt import SLOT_KINDS
from helios.narrative.verifier import direction_of, edge_holds, names_in
from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance

if TYPE_CHECKING:
    from collections.abc import Mapping

    from helios.narrative.params import NarratorParams

__all__ = ["MAX_CLAIMS", "slot_schema"]

MAX_CLAIMS = 3  # per slot; verification steps are capped by params.max_steps
_SENTENCE = {"type": "string", "maxLength": 240}
_SNIPPET = {"type": "string", "maxLength": 160}
_CHANNELS = ("error", "latency", "resource")
_MODALITY_PREFIX = {"metric": "D:", "log": "L:", "edge": "G:"}
_PIPELINE_PREFIX = {"dpipe": "D:", "gpipe": "G:", "lpipe": "L:"}


def _evidence(entry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Citable items in entry order (worker claims are not evidence)."""
    return [
        i
        for s in entry["steps"]
        for i in s.get("items", [])
        if ":claim" not in str(i["id"])
    ]


def _cites(ids: list[str], *, most: int = 1) -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"enum": ids},
        "minItems": 1,
        "maxItems": min(most, len(ids)),
    }


def _option(
    kind: ClaimKind, fields: dict[str, Any], cites: dict[str, Any]
) -> dict[str, Any]:
    # Fields before the sentence: the model settles what it claims, then words it.
    props = {
        "kind": {"const": kind.value},
        **fields,
        "cites": cites,
        "sentence": _SENTENCE,
    }
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


def _ranking(ranked: list[str]) -> list[dict[str, Any]]:
    return [
        _option(
            ClaimKind.RANKING,
            {"service": {"const": svc}, "rank": {"const": n}},
            _cites(["F"]),
        )
        for n, svc in enumerate(ranked[:3], start=1)
    ]


def _shifts(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i in items:
        parts = str(i["id"]).split(":")
        if len(parts) != 3 or parts[0] != "D" or parts[2] not in _CHANNELS:
            continue
        direction = direction_of(i)
        if direction is None:
            continue
        out.append(
            _option(
                ClaimKind.SHIFT,
                {
                    "service": {"const": parts[1]},
                    "channel": {"const": parts[2]},
                    "direction": {"const": direction},
                },
                _cites([str(i["id"])]),
            )
        )
    return out


def _edges(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i in items:
        if not str(i["id"]).startswith("G:"):
            continue
        callee = str(i.get("service"))
        value = i.get("value")
        pairs: list[tuple[str, str, str]] = []
        if str(i["id"]).endswith(":wait_from"):
            pairs = [(c, callee, "wait") for c in sorted(names_in(value))]
        elif str(i["id"]).endswith(":leads"):
            pairs = [(c, callee, "lead") for c in sorted(names_in(value))]
        elif str(i["id"]).endswith(":ghost_edges") and isinstance(value, list):
            pairs = [
                (str(p[0]), str(p[1]), "ghost")
                for p in value
                if isinstance(p, list) and len(p) == 2
            ]
        for caller, to, feature in pairs:
            probe = Claim(
                kind=ClaimKind.CALL_STRUCTURE,
                sentence="",
                caller=caller,
                callee=to,
                feature=feature,
            )
            if edge_holds(probe, i):
                out.append(
                    _option(
                        ClaimKind.CALL_STRUCTURE,
                        {
                            "caller": {"const": caller},
                            "callee": {"const": to},
                            "feature": {"const": feature},
                        },
                        _cites([str(i["id"])]),
                    )
                )
    return out


def _logs(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        _option(
            ClaimKind.LOG_MESSAGE,
            {"service": {"const": str(i.get("service"))}, "snippet": _SNIPPET},
            _cites([str(i["id"])]),
        )
        for i in items
        if str(i["id"]).startswith("L:") and i.get("service") and i.get("text")
    ]


def _contradictions(
    entry: Mapping[str, Any], items: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    steps = {str(s["id"]): s for s in entry["steps"]}
    out = []
    for pipeline in steps["F"].get("disagree") or []:
        ranked = list(steps.get(f"P:{pipeline}", {}).get("ranked") or [])
        if pipeline not in _PIPELINE_PREFIX or not ranked:
            continue
        own = [
            str(i["id"])
            for i in items
            if str(i["id"]).startswith(_PIPELINE_PREFIX[pipeline])
            and i.get("service") == ranked[0]
        ]
        if own:
            out.append(
                _option(
                    ClaimKind.CONTRADICTION,
                    {"pipeline": {"const": pipeline}, "service": {"const": ranked[0]}},
                    _cites(own, most=2),
                )
            )
    return out


def _steps(
    ranked: list[str], items: list[Mapping[str, Any]], params: NarratorParams
) -> list[dict[str, Any]]:
    out = []
    for modality, prefix in _MODALITY_PREFIX.items():
        ids = [
            str(i["id"])
            for i in items
            if str(i["id"]).startswith(prefix) and i.get("service") in ranked[:3]
        ]
        if ids:
            out.append(
                _option(
                    ClaimKind.VERIFICATION_STEP,
                    {
                        "target_service": {"enum": ranked[:3]},
                        "action_verb": {"enum": list(params.verbs)},
                        "modality": {"const": modality},
                    },
                    _cites(ids, most=2),
                )
            )
    return out


def slot_schema(
    slot: str, entry: Mapping[str, Any], params: NarratorParams
) -> dict[str, Any] | None:
    """The JSON schema of one slot's answer, or None when nothing fits it."""
    steps = {str(s["id"]): s for s in entry["steps"]}
    ranked = list(steps["F"].get("ranked") or [])
    items = _evidence(entry)
    builders = {
        "ranking": lambda: _ranking(ranked),
        "shift": lambda: _shifts(items),
        "call_structure": lambda: _edges(items),
        "log_message": lambda: _logs(items),
        "contradiction": lambda: _contradictions(entry, items),
        "verification_step": lambda: _steps(ranked, items, params),
    }
    options = [o for kind in SLOT_KINDS[slot] for o in builders[kind]()]
    if not options:
        return None
    most = params.max_steps if slot == "verification" else MAX_CLAIMS
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {"anyOf": options},
                "minItems": 1,
                "maxItems": most,
            }
        },
        "required": ["claims"],
        "additionalProperties": False,
    }
