"""Resolution des seuils par date (thresholds.ThresholdResolver)."""

from __future__ import annotations

from datetime import date

from database import get_session
from models import AthleteThreshold, Discipline
from thresholds import ThresholdResolver


def test_resolver_falls_back_to_profile_without_rows():
    r = ThresholdResolver()
    s = r.seuils_for("course", date(2026, 8, 1))
    # profil par defaut : FC max 200, seuil ~ 0.9 * max
    assert s.fc_max == 200
    assert abs(s.fc_seuil - 180) < 0.1
    assert s.allure_seuil_course_s_km is None


def test_resolver_picks_latest_valid_row_by_date():
    with get_session() as db:
        db.add_all([
            AthleteThreshold(
                date_debut_validite=date(2026, 1, 1), discipline=Discipline.course,
                fc_seuil=170, allure_seuil_s=320.0,
            ),
            AthleteThreshold(
                date_debut_validite=date(2026, 6, 1), discipline=Discipline.course,
                fc_seuil=175, allure_seuil_s=300.0,
            ),
        ])

    r = ThresholdResolver()
    # avant le 1er juin : ancienne ligne
    s1 = r.seuils_for("course", date(2026, 3, 1))
    assert s1.fc_seuil == 170 and s1.allure_seuil_course_s_km == 320.0
    # apres : nouvelle ligne
    s2 = r.seuils_for("course", date(2026, 7, 1))
    assert s2.fc_seuil == 175 and s2.allure_seuil_course_s_km == 300.0
    # avant toute ligne : profil
    s0 = r.seuils_for("course", date(2025, 1, 1))
    assert s0.allure_seuil_course_s_km is None


def test_resolver_maps_run_subsports_to_course_discipline():
    with get_session() as db:
        db.add(AthleteThreshold(
            date_debut_validite=date(2020, 1, 1), discipline=Discipline.course,
            allure_seuil_s=300.0,
        ))
    r = ThresholdResolver()
    # "course" couvre marche / rando / trail / tapis
    assert r.seuils_for("course", date(2026, 1, 1)).allure_seuil_course_s_km == 300.0
