"""Reclassement sport/sous_type des seances existantes (scripts.reclassify_sports)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from core.database import get_session
from core.models import Session, SourceFormat, Sport
from scripts.reclassify_sports import _apply, _planned_changes


def _add(source_file: str, sport: str, sous_type: str | None) -> None:
    with get_session() as db:
        db.add(
            Session(
                date=date(2024, 1, 1),
                sport=Sport(sport),
                sous_type=sous_type,
                duree_s=3600,
                source_file=source_file,
                source_key=source_file.rsplit(".", 1)[0],
                source_format=SourceFormat.fit,
            )
        )


def test_reclassify_walking_and_indoor_cycling():
    # jadis classees "autre" / "velo sans sous_type" par l'ancienne logique
    _add("2025-09-25_09.41.03-walking.fit", "autre", None)
    _add("2026-07-09_20.06.26-indoor_cycling.fit", "velo", None)
    _add("2024-06-11_16.46.42-running.fit", "course", None)
    # deja correcte : ne doit pas apparaitre dans le plan
    _add("2023-06-07_17.35.26-swimming.fit", "natation", "piscine")

    changes = _planned_changes()
    by_id = {c[0]: (c[3], c[4]) for c in changes}
    assert len(changes) == 3

    n = _apply(changes)
    assert n == 3

    with get_session() as db:
        rows = {
            s.source_file: (s.sport.value, s.sous_type)
            for s in db.scalars(select(Session)).all()
        }
    assert rows["2025-09-25_09.41.03-walking.fit"] == ("course", "marche")
    assert rows["2026-07-09_20.06.26-indoor_cycling.fit"] == ("velo", "home_trainer")
    assert rows["2024-06-11_16.46.42-running.fit"] == ("course", "course")
    assert rows["2023-06-07_17.35.26-swimming.fit"] == ("natation", "piscine")


def test_reclassify_is_idempotent():
    _add("2025-09-25_09.41.03-walking.fit", "autre", None)
    _apply(_planned_changes())
    assert _planned_changes() == []


def test_reclassify_ignores_unknown_token_and_manual():
    _add("manuel-2024-01-01-course-60min", "course", None)  # pas de token -> None
    _add("2024-01-01_10.00.00-other_6.fit", "autre", None)  # token inconnu
    assert _planned_changes() == []
