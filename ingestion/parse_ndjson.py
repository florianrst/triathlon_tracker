"""Parsing NDJSON (export "donnees passives 24/7") -> agregation journaliere.

Une ligne JSON par echantillon, ~toutes les 10 min ::

    {"timestamp":"2026-06-02T20:10:00.000+02:00",
     "entryData":{"hr":1.1666666,"stepCount":11,"energyConsumption":0.0}}

ATTENTION : ``hr`` n'est PAS un bpm (valeurs ~0.8-2.5) mais un indice/ratio
Suunto non calibre. On conserve donc le brut agrege (min / moyenne du ratio)
et on laisse ``hr_repos_estime`` a NULL tant que le champ n'est pas clarifie
avec l'utilisateur. ``stepCount`` est traite comme un increment par
echantillon (somme sur la journee) ; ``energyConsumption`` idem.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path


def _parse_ts(raw: str) -> datetime:
    # datetime.fromisoformat gere l'offset "+02:00" depuis Python 3.11
    return datetime.fromisoformat(raw)


def aggregate_ndjson(path: str | os.PathLike) -> list[dict]:
    """Retourne une liste de dicts prets pour la table ``daily_passive``."""
    path = Path(path)
    buckets: dict[date, dict] = defaultdict(
        lambda: {"hr": [], "steps": 0.0, "energie": 0.0, "n": 0}
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
            hr = entry.get("hr")
            if isinstance(hr, (int, float)) and hr > 0:
                b["hr"].append(float(hr))
            step = entry.get("stepCount")
            if isinstance(step, (int, float)):
                b["steps"] += float(step)
            en = entry.get("energyConsumption")
            if isinstance(en, (int, float)):
                b["energie"] += float(en)

    rows: list[dict] = []
    for day, b in sorted(buckets.items()):
        hr = b["hr"]
        rows.append(
            {
                "date": day,
                "hr_ratio_min": min(hr) if hr else None,
                "hr_ratio_moy": sum(hr) / len(hr) if hr else None,
                "hr_repos_estime": None,  # non calibre : cf. docstring
                "steps_total": int(round(b["steps"])) or None,
                "energie_totale": b["energie"] or None,
                "n_echantillons": b["n"],
            }
        )
    return rows
