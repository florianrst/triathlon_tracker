"""Memoire utilisateur persistee en markdown (``user/*.md``).

Distinct de ``data/incoming/**/user/user.json`` (export brut Suunto, lu par
``athlete.py``). Ce module gere le profil "libre" (objectifs, contraintes,
preferences...) et le resume des conversations passees avec le chat Claude.

Convention "on date, on historise" appliquee au markdown : on ajoute des
sections datees en fin de fichier, on ne reecrit jamais le contenu existant.
Une info qui change se traduit par une nouvelle section qui prevaut sur les
precedentes a la lecture, exactement le principe deja utilise pour
``athlete_thresholds`` / ``zone_sets`` en base, transpose au texte.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from athlete.profil import Profil, load_profil

BASE_DIR = Path(__file__).resolve().parent
USER_DIR = BASE_DIR / "user"
PROFIL_MD = USER_DIR / "profil.md"
CONVERSATIONS_MD = USER_DIR / "conversations.md"

_PROFIL_HEADER = "# Profil (informations libres)\n"
_CONV_HEADER = "# Resume des echanges passes\n"


def _ensure(path: Path, header: str) -> None:
    USER_DIR.mkdir(exist_ok=True)
    if not path.exists():
        path.write_text(header + "\n", encoding="utf-8")


def _append_section(path: Path, header: str, titre: str, corps: str) -> None:
    _ensure(path, header)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {titre}\n{corps.strip()}\n")


def append_profil_note(note: str, *, quand: date | None = None) -> None:
    """Ajoute une section datee au fichier profil (jamais d'ecrasement)."""
    _append_section(PROFIL_MD, _PROFIL_HEADER, (quand or date.today()).isoformat(), note)


def append_conversation_summary(resume: str, *, page: str, quand: date | None = None) -> None:
    """Ajoute un resume de conversation, tague par page d'origine."""
    titre = f"{(quand or date.today()).isoformat()} (page: {page})"
    _append_section(CONVERSATIONS_MD, _CONV_HEADER, titre, resume)


def read_profil_markdown() -> str:
    _ensure(PROFIL_MD, _PROFIL_HEADER)
    return PROFIL_MD.read_text(encoding="utf-8")


def read_conversations_markdown() -> str:
    _ensure(CONVERSATIONS_MD, _CONV_HEADER)
    return CONVERSATIONS_MD.read_text(encoding="utf-8")


@dataclass(frozen=True)
class ContexteUtilisateur:
    """Fusion des donnees numeriques (``athlete.Profil``) et du profil libre (markdown)."""

    profil_numerique: Profil
    profil_libre_md: str
    historique_conversations_md: str


def charger_contexte_utilisateur() -> ContexteUtilisateur:
    """Point d'entree unique pour ``ui/chat.py`` : fusionne ``athlete.load_profil()``
    (fc_max/fc_repos/poids_kg, source ``data/incoming/**/user/user.json``) avec le
    profil libre et le resume des conversations passees (``user/*.md``)."""
    return ContexteUtilisateur(
        profil_numerique=load_profil(),
        profil_libre_md=read_profil_markdown(),
        historique_conversations_md=read_conversations_markdown(),
    )
