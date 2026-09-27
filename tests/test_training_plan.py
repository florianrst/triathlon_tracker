"""Tests de training_plan.py (calcul de duree, formatage des blocs)."""

from __future__ import annotations

from training_plan import duree_totale_s, formater_bloc, formater_duree


def test_duree_totale_s_somme_duree_fois_repetitions():
    blocs = [
        {"type": "echauffement", "duree_s": 600, "repetitions": 1},
        {"type": "travail", "duree_s": 180, "repetitions": 6},
        {"type": "recuperation", "duree_s": 120, "repetitions": 6},
        {"type": "retour_calme", "duree_s": 300, "repetitions": 1},
    ]
    # 600 + 6*180 + 6*120 + 300 = 600 + 1080 + 720 + 300 = 2700
    assert duree_totale_s(blocs) == 2700


def test_duree_totale_s_ignore_blocs_en_distance():
    blocs = [
        {"type": "travail", "distance_m": 400, "repetitions": 8},
        {"type": "echauffement", "duree_s": 600},
    ]
    assert duree_totale_s(blocs) == 600


def test_duree_totale_s_liste_vide():
    assert duree_totale_s([]) == 0


def test_formater_duree():
    assert formater_duree(185) == "3:05"
    assert formater_duree(60) == "1:00"


def test_formater_bloc_avec_repetitions_et_zone():
    b = {"type": "travail", "duree_s": 180, "repetitions": 6, "zone_cible": "Z4", "notes": "cote a cote"}
    assert formater_bloc(b) == "6 x 3:00 travail @ Z4 — cote a cote"


def test_formater_bloc_simple_en_distance():
    b = {"type": "travail", "distance_m": 400}
    assert formater_bloc(b) == "400 m travail"
