"""Aide a la construction/lecture des seances planifiees (blocs structures,
proche d'un "workout" TrainingPeaks). Utilise par ``pages/7_entrainements.py``.

Un bloc est un dict simple :
``{"type": "travail", "duree_s": 180, "distance_m": None, "repetitions": 6,
"zone_cible": "Z4", "notes": "..."}`` - stocke tel quel dans
``PlannedWorkout.blocs_json``.
"""

from __future__ import annotations

TYPES_BLOC = ["echauffement", "travail", "recuperation", "retour_calme"]
ZONES_CIBLES = ["Z1", "Z2", "Z3", "Z4", "Z5"]


def duree_totale_s(blocs: list[dict]) -> int:
    """Somme ``duree_s * repetitions`` sur les blocs qui ont une duree.

    Les blocs en distance (natation en metres, par ex.) ne sont pas comptes
    dans le temps total : l'allure n'est pas connue a priori.
    """
    total = 0
    for b in blocs:
        duree = b.get("duree_s")
        if duree:
            total += int(duree) * int(b.get("repetitions") or 1)
    return total


def formater_duree(secondes: int) -> str:
    m, s = divmod(int(secondes), 60)
    return f"{m}:{s:02d}"


def formater_bloc(b: dict) -> str:
    """Rendu texte compact d'un bloc, ex. ``6 x 3:00 travail @ Z4 — cote a cote``."""
    rep = int(b.get("repetitions") or 1)
    prefix = f"{rep} x " if rep > 1 else ""
    if b.get("duree_s"):
        mesure = formater_duree(b["duree_s"])
    elif b.get("distance_m"):
        mesure = f"{b['distance_m']:.0f} m"
    else:
        mesure = "?"
    zone_txt = f" @ {b['zone_cible']}" if b.get("zone_cible") else ""
    label = b.get("type", "bloc")
    txt = f"{prefix}{mesure} {label}{zone_txt}"
    if b.get("notes"):
        txt += f" — {b['notes']}"
    return txt
