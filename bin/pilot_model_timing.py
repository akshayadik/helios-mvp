#!/usr/bin/env python3
"""S5.3 L6: time larger local models against the 8B on build worker prompts.

    poetry run python bin/pilot_model_timing.py \
        --out docs/sprints/s5-integration-freeze/pilot/l6_model_timing.json

Design s5_3_pilot_design.md Q-f (owner, 2026-11-15): speed and parser
acceptance only. Nothing is scored, nothing enters an analysis, and the
response cache is read (to confirm each rebuilt prompt is the one the 8B
answered) but never written.

Prompts: per campaign, the L-pipe evidence of HELIOS-noRouter runs (every
worker call of a case), one prompt per (case, worker) with a non-empty
digest, ordered by SHA-256 of (incident, worker) and the first ``--per`` kept.
Each prompt is rebuilt with ``personas.render_prompt`` from the stored
candidates and digest lines. ``exact`` records whether its cache key is in
the response cache under the 8B's digest, i.e. the rebuilt prompt is
byte-identical to the one sent in S5.1.

Per model: one warm-up call (load time, excluded), then every prompt once
with Protocol A decoding. Acceptance follows ``workers.run_worker``: the
answer parses against the worker schema, keeps its allowed values, and ranks
at least one candidate with a valid citation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from helios.vcl import VCLFlag  # noqa: E402, F401 — flag-guard compliance

HELIOS_ENABLE_PILOT_MODEL_TIMING: bool = True
MODELS = ("llama3.1:8b", "qwen2.5-coder:14b", "devstral:24b", "qwen3-coder:30b")
CAMPAIGNS = ("otel_build_v3", "rcaeval_build_1")
FIRST_RUN = "HELIOS-noRouter"


def pick_prompts(dirs: list[Path], per: int) -> list[dict[str, Any]]:
    """Up to ``per`` (case, worker) prompts per campaign, rebuilt from evidence."""
    import duckdb

    from helios.pipelines.l_pipe.aliases import build_alias_map
    from helios.pipelines.l_pipe.digests import Digest, DigestLine
    from helios.pipelines.l_pipe.personas import PERSONAS, prompt_sha, render_prompt

    personas = {p.name: p for p in PERSONAS}
    out: list[dict[str, Any]] = []
    for d in dirs:
        runs = {
            str(r["run_id"])
            for r in map(json.loads, (d / "campaign_log.jsonl").open())
            if r.get("event") == "passed"
            and str(r.get("key", "")).startswith("confirmatory/")
            and str(r["key"]).endswith("/" + FIRST_RUN)
        }
        con = duckdb.connect(str(d / "results.duckdb"), read_only=True)
        rows = con.execute(
            "select run_id, incident_id, evidence_json from evidence_row"
            " where pipeline = 'lpipe'"
        ).fetchall()
        con.close()
        found: list[tuple[str, dict[str, Any]]] = []
        for run_id, incident, ev_json in rows:
            if run_id not in runs:
                continue
            ev = json.loads(ev_json)
            for worker, rec in (ev.get("digests") or {}).items():
                lines = (rec or {}).get("lines") or []
                if not lines:
                    continue
                digest = Digest(
                    worker,
                    tuple(DigestLine(i, s, t, 0) for i, s, t in lines),
                    int(rec.get("cut") or 0),
                )
                alias = build_alias_map(incident, ev["candidates"], [])
                persona = personas[worker]
                try:
                    prompt = render_prompt(persona, digest, alias)
                except Exception:
                    continue
                order = hashlib.sha256(f"{incident}\x00{worker}".encode()).hexdigest()
                found.append(
                    (
                        order,
                        {
                            "campaign": d.name,
                            "incident_id": incident,
                            "worker": worker,
                            "prompt": prompt,
                            "prompt_sha": prompt_sha(persona),
                            "model_digest": ev.get("model_digest") or "",
                            "digest": digest,
                            "alias": alias,
                        },
                    )
                )
        found.sort(key=lambda x: x[0])
        out.extend(p for _, p in found[:per])
    return out


def accepted(raw: str, digest: Any, alias: Any) -> bool:
    """The worker's validation (workers.run_worker) passes with a ranking."""
    from pydantic import ValidationError

    from helios.pipelines.l_pipe.response_handler import sanitize_llm_output
    from helios.pipelines.l_pipe.workers import _AnswerIn, _fails_schema, _validate

    try:
        answer = _AnswerIn.model_validate(json.loads(sanitize_llm_output(raw)))
    except (json.JSONDecodeError, ValidationError):
        return False
    if _fails_schema(answer, digest, alias):
        return False
    ranked, _ = _validate(answer, digest, alias)
    return bool(ranked)


def summarise(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "p90": None, "mean": None}
    v = sorted(values)
    return {
        "median": round(statistics.median(v), 2),
        "p90": round(v[max(math.ceil(len(v) * 9 / 10) - 1, 0)], 2),
        "mean": round(statistics.fmean(v), 2),
    }


def time_model(model: str, prompts: list[dict[str, Any]]) -> dict[str, Any]:
    from helios.pipelines.l_pipe.lpipe_config import OLLAMA_BASE_URL, TIMEOUT_S
    from helios.pipelines.l_pipe.ollama_client import OllamaClient

    client = OllamaClient(OLLAMA_BASE_URL, model)
    t0 = time.monotonic()
    client.generate(prompts[0]["prompt"], timeout_s=TIMEOUT_S * 4)
    load_s = time.monotonic() - t0
    walls, gen_rates, n_ok, errors = [], [], 0, 0
    per_prompt = []
    for p in prompts:
        t1 = time.monotonic()
        try:
            res = client.generate(p["prompt"], timeout_s=TIMEOUT_S * 4)
        except Exception as exc:
            errors += 1
            per_prompt.append({"ok": False, "error": type(exc).__name__})
            continue
        wall = time.monotonic() - t1
        ok = accepted(res.text, p["digest"], p["alias"])
        n_ok += ok
        walls.append(wall)
        if res.compute_ms and res.completion_tokens:
            gen_rates.append(res.completion_tokens / (res.compute_ms / 1000))
        per_prompt.append(
            {
                "ok": ok,
                "wall_s": round(wall, 2),
                "prompt_tokens": res.prompt_tokens,
                "completion_tokens": res.completion_tokens,
            }
        )
    return {
        "model": model,
        "load_and_first_call_s": round(load_s, 1),
        "wall_s": summarise(walls),
        "tokens_per_s_compute": summarise(gen_rates),
        "accepted": n_ok,
        "errors": errors,
        "prompts": len(prompts),
        "per_prompt": per_prompt,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT / "data/campaigns/s5_1")
    ap.add_argument("--per", type=int, default=10)
    ap.add_argument("--models", nargs="+", default=list(MODELS))
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if not HELIOS_ENABLE_PILOT_MODEL_TIMING:
        print("pilot model timing disabled", file=sys.stderr)
        return 1
    from helios.pipelines.l_pipe.cache import cache_key

    prompts = pick_prompts([args.root / c for c in CAMPAIGNS], args.per)
    cache_db = REPO_ROOT / "data/cache/lpipe_cache.sqlite"
    import sqlite3

    con = sqlite3.connect(f"file:{cache_db}?mode=ro", uri=True)
    for p in prompts:
        key = cache_key(p["model_digest"], p["prompt_sha"], p["prompt"])
        hit = con.execute("select 1 from calls where key = ?", (key,)).fetchone()
        p["exact"] = hit is not None
    con.close()
    print(
        f"{len(prompts)} prompts, {sum(p['exact'] for p in prompts)} byte-identical"
        " to the S5.1 calls",
        flush=True,
    )
    results = []
    for model in args.models:
        r = time_model(model, prompts)
        print(
            f"{model}: load {r['load_and_first_call_s']} s, median "
            f"{r['wall_s']['median']} s/call, accepted {r['accepted']}/"
            f"{r['prompts']}, errors {r['errors']}",
            flush=True,
        )
        results.append(r)
    report = {
        "prompts": [
            {k: p[k] for k in ("campaign", "incident_id", "worker", "exact")}
            for p in prompts
        ],
        "models": results,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
