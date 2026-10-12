"""Tests de persistance du modele PlannedWorkout (bibliotheque de seances)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from core.database import engine, get_session
from core.models import PlannedWorkout, Sport, StatutSeance, TypeSeance
from core.training_plan import duree_totale_s


def _blocs():
    return [
        {"type": "echauffement", "duree_s": 600, "repetitions": 1, "zone_cible": "Z1", "notes": None},
        {"type": "travail", "duree_s": 180, "repetitions": 6, "zone_cible": "Z4", "notes": None},
        {"type": "recuperation", "duree_s": 120, "repetitions": 6, "zone_cible": "Z1", "notes": None},
    ]


def test_creation_sans_date_reste_en_bibliotheque():
    blocs = _blocs()
    with get_session() as db:
        db.add(PlannedWorkout(
            titre="Seuil 6x3min",
            sport=Sport.velo,
            type_seance=TypeSeance.seuil,
            date_prevue=None,
            statut=StatutSeance.prevue,
            blocs_json=blocs,
            duree_estimee_s=duree_totale_s(blocs),
        ))

    with get_session() as db:
        obj = db.scalars(select(PlannedWorkout)).one()
        assert obj.date_prevue is None
        assert obj.statut == StatutSeance.prevue
        assert len(obj.blocs_json) == 3
        assert obj.duree_estimee_s == 600 + 6 * 180 + 6 * 120


def test_planifiee_puis_rattachee_a_une_seance_reelle():
    with get_session() as db:
        db.add(PlannedWorkout(
            titre="Sortie longue",
            sport=Sport.course,
            type_seance=TypeSeance.endurance,
            date_prevue=date(2026, 10, 1),
            statut=StatutSeance.prevue,
            blocs_json=[{"type": "travail", "duree_s": 3600, "repetitions": 1}],
        ))

    with get_session() as db:
        obj = db.scalars(select(PlannedWorkout)).one()
        obj.session_id = 42
        obj.statut = StatutSeance.realisee

    with get_session() as db:
        obj = db.scalars(select(PlannedWorkout)).one()
        assert obj.statut == StatutSeance.realisee
        assert obj.session_id == 42
