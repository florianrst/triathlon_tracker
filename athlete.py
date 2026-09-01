"""Profil athlete : constantes physiologiques par defaut.

Il n'existe pas de table de profil dans l'app. On lit les quelques valeurs
utiles (FC max, FC repos, poids) depuis l'export Suunto si present
(``data/incoming/**/user/user.json``), sinon on retombe sur des defauts
raisonnables. Ces valeurs ne servent que de FALLBACK au calcul de charge
quand aucune ligne ``athlete_thresholds`` ne couvre la date d'une seance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from database import INCOMING_DIR

FC_MAX_DEFAUT = 200
FC_REPOS_DEFAUT = 60
POIDS_KG_DEFAUT = 68.0


@dataclass(frozen=True)
class Profil:
    fc_max: int = FC_MAX_DEFAUT
    fc_repos: int = FC_REPOS_DEFAUT
    poids_kg: float = POIDS_KG_DEFAUT

    @property
    def fc_seuil_estime(self) -> float:
        """Faute de test : ~90 % de la FC max (approximation LTHR courante)."""
        return round(0.90 * self.fc_max, 1)


@lru_cache(maxsize=1)
def load_profil() -> Profil:
    for user_json in INCOMING_DIR.rglob("user/user.json"):
        try:
            data = json.loads(user_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return Profil(
            fc_max=int(data.get("hrMax") or FC_MAX_DEFAUT),
            fc_repos=int(data.get("hrRest") or FC_REPOS_DEFAUT),
            poids_kg=float(data.get("weight") or POIDS_KG_DEFAUT),
        )
    return Profil()
