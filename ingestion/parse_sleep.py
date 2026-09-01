"""Parsing NDJSON sommeil (export Suunto) -> agregation par jour de reveil.

Une ligne JSON par segment de sommeil, le ``timestamp`` marque la FIN du
segment (heure de reveil) ::

    {"timestamp":"2026-08-01T01:43:40.837+02:00",
     "entryData":{"deepSleepDuration":3130.0,"duration":26569.0,
                  "hrAvg":0.75,"hrMin":0.55,"quality":0.92}}

Regle de rattachement au "jour de reveil" :
- timestamp le soir (>= 18 h) -> on dort cette nuit, reveil demain -> jour +1 ;
- sinon -> jour meme.
Les segments d'une meme nuit (sommeil fractionne, sieste du matin) tombent
alors dans le meme bucket et sont sommes.

ATTENTION : ``hrAvg`` / ``hrMin`` ne sont PAS des bpm mais un ratio Suunto non
calibre (~0.55-1.0), comme le ``hr`` de ``parse_ndjson``. On conserve le brut.
``duration`` et ``deepSleepDuration`` sont en SECONDES.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

# heure a partir de laquelle un segment de sommeil est rattache au lendemain
_EVENING_HOUR = 18


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw)  # gere l'offset "+02:00" (Python >= 3.11)


def _wake_day(ts: datetime) -> date:
    return ts.date() + timedelta(days=1) if ts.hour >= _EVENING_HOUR else ts.date()


def aggregate_sleep_ndjson(path: str | os.PathLike) -> list[dict]:
    """Retourne une liste de dicts prets pour la table ``sleep_daily``."""
    path = Path(path)
    buckets: dict[date, dict] = defaultdict(
        lambda: {"duree": 0.0, "profond": 0.0, "qual": [], "qual_w": [], "hr": [], "hrmin": [], "n": 0}
    )
    # certains exports Suunto dupliquent chaque segment -> dedup sur (ts, duree)
    seen: set[tuple[str, float]] = set()

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
            dedup_key = (ts_raw, float(entry.get("duration") or 0.0))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            try:
                day = _wake_day(_parse_ts(ts_raw))
            except ValueError:
                continue

            b = buckets[day]
            b["n"] += 1
            dur = entry.get("duration")
            if isinstance(dur, (int, float)) and dur > 0:
                b["duree"] += float(dur)
                q = entry.get("quality")
                if isinstance(q, (int, float)):
                    b["qual"].append(float(q))
                    b["qual_w"].append(float(dur))  # moyenne de qualite ponderee duree
            deep = entry.get("deepSleepDuration")
            if isinstance(deep, (int, float)) and deep >= 0:
                b["profond"] += float(deep)
            hr = entry.get("hrAvg")
            if isinstance(hr, (int, float)) and hr > 0:
                b["hr"].append(float(hr))
            hrmin = entry.get("hrMin")
            if isinstance(hrmin, (int, float)) and hrmin > 0:
                b["hrmin"].append(float(hrmin))

    rows: list[dict] = []
    for day, b in sorted(buckets.items()):
        qual = None
        if b["qual"] and sum(b["qual_w"]) > 0:
            qual = sum(q * w for q, w in zip(b["qual"], b["qual_w"])) / sum(b["qual_w"])
        rows.append(
            {
                "date": day,
                "duree_totale_s": int(round(b["duree"])) or None,
                "sommeil_profond_s": int(round(b["profond"])) or None,
                "qualite": qual,
                "hr_nuit_moy": sum(b["hr"]) / len(b["hr"]) if b["hr"] else None,
                "hr_nuit_min": min(b["hrmin"]) if b["hrmin"] else None,
                "n_segments": b["n"],
            }
        )
    return rows
