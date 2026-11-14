"""Read-only access to one campaign's stored runs (S4.1 A-c).

Opens the DuckDB store with ``read_only=True`` (never ``ResultStore``, which
runs schema migrations), and reads only the tables HELIOS writes at run time:
``fusion_row``, ``narrative_row``, ``trigger_row``, ``routing_row`` and
``result_row``. The scored tables (``eval_score``, ``eval_run``) and the
baseline table are never read: they carry or derive from ground truth.

DuckDB allows one writer process per file; a read-only open fails while a
campaign writes to the store, so the API serves a store no campaign is
writing to.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import duckdb

from helios.vcl import VCLFlag  # noqa: F401 — flag-guard compliance
from helios.vcl.variants import CONFIRMATORY_VARIANTS, EXPLORATORY_VARIANTS

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["RunVariant", "StoreReader", "variant_catalogue"]


@dataclass(frozen=True)
class RunVariant:
    name: str
    narrative: bool  # coe_narrative: False for HELIOS-noExpl (E-H7)


def variant_catalogue() -> dict[str, RunVariant]:
    """variant_config_hash -> name and whether its narrative may be shown."""
    out: dict[str, RunVariant] = {}
    for name, manifest in {**CONFIRMATORY_VARIANTS, **EXPLORATORY_VARIANTS}.items():
        out[manifest.compute_variant_config_hash()] = RunVariant(
            name, bool(manifest.coe_narrative)
        )
    return out


def _rows(cur: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    cols = [d[0] for d in cur.description or []]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


class StoreReader:
    """SELECTs over one campaign store, opened read-only."""

    def __init__(self, path: Path) -> None:
        self._con = duckdb.connect(str(path), read_only=True)
        self._variants = variant_catalogue()

    def close(self) -> None:
        self._con.close()

    def schema_tags(self) -> list[str]:
        cur = self._con.execute("SELECT tag FROM schema_tag ORDER BY tag")
        return [str(r[0]) for r in cur.fetchall()]

    def variant(self, config_hash: str) -> RunVariant:
        return self._variants.get(config_hash, RunVariant("unknown", False))

    def count_incidents(self) -> int:
        row = self._con.execute(
            "SELECT count(DISTINCT incident_id) FROM fusion_row"
        ).fetchone()
        return int(row[0]) if row else 0

    def incidents(self, limit: int, offset: int) -> list[dict[str, Any]]:
        """One row per incident: run count and verdict states, by incident ID."""
        cur = self._con.execute(
            "SELECT incident_id, count(*) AS runs, "
            "count(*) FILTER (WHERE state = 'confirmed') AS confirmed, "
            "count(*) FILTER (WHERE state <> 'confirmed') AS needs_review "
            "FROM fusion_row GROUP BY incident_id ORDER BY incident_id "
            "LIMIT ? OFFSET ?",
            [limit, offset],
        )
        return _rows(cur)

    def runs_of(self, incident_id: str) -> list[dict[str, Any]]:
        cur = self._con.execute(
            "SELECT f.run_id, f.incident_id, f.variant_config_hash, f.state, "
            "f.confidence, f.ranked_json, t.stored_at "
            "FROM fusion_row f LEFT JOIN trigger_row t USING (run_id) "
            "WHERE f.incident_id = ? ORDER BY t.stored_at, f.run_id",
            [incident_id],
        )
        return _rows(cur)

    def fusion(self, run_id: str) -> dict[str, Any] | None:
        rows = _rows(
            self._con.execute("SELECT * FROM fusion_row WHERE run_id = ?", [run_id])
        )
        return rows[0] if rows else None

    def trigger(self, run_id: str) -> dict[str, Any] | None:
        rows = _rows(
            self._con.execute(
                "SELECT trigger_time_s, suspects, source, stored_at "
                "FROM trigger_row WHERE run_id = ?",
                [run_id],
            )
        )
        return rows[0] if rows else None

    def routing(self, run_id: str) -> dict[str, Any] | None:
        row = self._con.execute(
            "SELECT routing_json FROM routing_row WHERE run_id = ?", [run_id]
        ).fetchone()
        return json.loads(str(row[0])) if row else None

    def narrative(self, run_id: str) -> dict[str, Any] | None:
        rows = _rows(
            self._con.execute(
                "SELECT narrator, rendered, slots_json, fallbacks "
                "FROM narrative_row WHERE run_id = ?",
                [run_id],
            )
        )
        return rows[0] if rows else None

    def phase(self, run_id: str) -> str | None:
        """The run's evaluation phase (from its pipeline rows)."""
        row = self._con.execute(
            "SELECT evaluation_phase FROM result_row WHERE run_id = ? LIMIT 1",
            [run_id],
        ).fetchone()
        return str(row[0]) if row else None
