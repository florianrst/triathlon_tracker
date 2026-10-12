"""Donnees de calibrage initiales (prepa Olympique 8 semaines du brief).

Idempotent : ne reinsere pas si un test du meme (date, discipline, type_test)
existe deja. A declencher depuis la page "Tests & zones".
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from core.database import get_session
from core.models import Discipline, ThresholdTest, ZoneSet

_CALIBRATION_DATE = date(2026, 6, 1)  # calage de reference (prepa precedente)

_TESTS = [
    dict(
        date=_CALIBRATION_DATE,
        discipline=Discipline.course,
        type_test="Cooper",
        valeur_brute=2.82,
        metrique_derivee="VMA 14.1 km/h",
        notes="Test Cooper prepa Olympique : 2.82 km en 12 min -> VMA 14.1 km/h.",
    ),
    dict(
        date=_CALIBRATION_DATE,
        discipline=Discipline.natation,
        type_test="Seuil observe",
        valeur_brute=75.0,
        metrique_derivee="Seuil haut 1'15/100m",
        notes="Z2 habituel 1'20/100m, seuil haut confirme 1'15/100m.",
    ),
]

_ZONES = [
    dict(
        date_debut_validite=_CALIBRATION_DATE,
        discipline=Discipline.course,
        zones_json={
            "reference": "VMA 14.1 km/h (Cooper)",
            "Z1": "> 6'04/km (recup active)",
            "Z2": "5'19-6'04/km (endurance fondamentale)",
            "Z3": "4'45-5'19/km (tempo)",
            "Z4": "4'15-4'45/km (seuil)",
            "Z5": "<= 4'15/km (VO2max)",
            "_note": "Zones allure du brief ; a re-ancrer sur SV1/SV2 quand test dispo.",
        },
    ),
    dict(
        date_debut_validite=_CALIBRATION_DATE,
        discipline=Discipline.natation,
        zones_json={
            "reference": "Seuil 1'15/100m",
            "Z2": "1'20/100m (endurance)",
            "seuil": "1'15/100m",
            "_note": "Calage prepa Olympique.",
        },
    ),
]


def seed_calibration() -> dict:
    inserted = {"tests": 0, "zones": 0}
    with get_session() as db:
        for t in _TESTS:
            dup = db.scalar(
                select(ThresholdTest.id).where(
                    ThresholdTest.date == t["date"],
                    ThresholdTest.discipline == t["discipline"],
                    ThresholdTest.type_test == t["type_test"],
                )
            )
            if not dup:
                db.add(ThresholdTest(**t))
                inserted["tests"] += 1

        for z in _ZONES:
            dup = db.scalar(
                select(ZoneSet.id).where(
                    ZoneSet.date_debut_validite == z["date_debut_validite"],
                    ZoneSet.discipline == z["discipline"],
                )
            )
            if not dup:
                db.add(ZoneSet(**z))
                inserted["zones"] += 1
    return inserted
