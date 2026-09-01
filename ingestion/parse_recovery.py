"""Parsing NDJSON recuperation / stress (export Suunto) -> agregation par jour.

Une ligne JSON par echantillon (~toutes les 30 min) ::

    {"timestamp":"2026-08-01T15:30:00.000+02:00",
     "entryData":{"balance":0.23,"stressState":4}}

- ``balance`` : indice de recuperation 0..1 (plus haut = mieux recupere).
- ``stressState`` : etat de stress discret 1..4 (1 = repos, 4 = stress eleve).

Agrege par jour civil : moyenne de ``balance``, minimum de ``balance``,
moyenne de ``stressState`` et part des echantillons a ``stressState >= 3``.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def aggregate_recovery_ndjson(path: str | os.PathLike) -> list[dict]:
    """Retourne une liste de dicts prets pour la table ``recovery_daily``."""
    path = Path(path)
    buckets: dict[date, dict] = defaultdict(
        lambda: {"balance": [], "stress": [], "stress_hi": 0, "n": 0}
    )

    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_raw = obj.get("timestamp")
            entry = obj.get("entryData") or {}
            if not ts_raw:
                continue
            try:
                day = _parse_ts(ts_raw).date()
            except ValueError:
                continue

            b = buckets[day]
            b["n"] += 1
            bal = entry.get("balance")
            if isinstance(bal, (int, float)):
                b["balance"].append(float(bal))
            ss = entry.get("stressState")
            if isinstance(ss, (int, float)):
                b["stress"].append(float(ss))
                if ss >= 3:
                    b["stress_hi"] += 1

    rows: list[dict] = []
    for day, b in sorted(buckets.items()):
        bal = b["balance"]
        stress = b["stress"]
        rows.append(
            {
                "date": day,
                "balance_moy": sum(bal) / len(bal) if bal else None,
                "balance_min": min(bal) if bal else None,
                "stress_moy": sum(stress) / len(stress) if stress else None,
                "pct_stress_eleve": b["stress_hi"] / len(stress) if stress else None,
                "n_echantillons": b["n"],
            }
        )
    return rows
