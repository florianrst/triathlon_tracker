"""Tests de user_memory.py : append (jamais d'ecrasement) + fusion avec athlete.py."""

from __future__ import annotations

from datetime import date

import pytest

import user_memory
from athlete import Profil


@pytest.fixture(autouse=True)
def _isole_user_dir(tmp_path, monkeypatch):
    """Redirige USER_DIR/PROFIL_MD/CONVERSATIONS_MD vers un dossier temporaire
    pour ne jamais toucher au vrai dossier `user/` du repo pendant les tests."""
    user_dir = tmp_path / "user"
    monkeypatch.setattr(user_memory, "USER_DIR", user_dir)
    monkeypatch.setattr(user_memory, "PROFIL_MD", user_dir / "profil.md")
    monkeypatch.setattr(user_memory, "CONVERSATIONS_MD", user_dir / "conversations.md")
    yield


def test_append_profil_note_cree_le_fichier_avec_entete():
    user_memory.append_profil_note("Objectif : 70.3 en mai 2027.", quand=date(2026, 9, 27))
    contenu = user_memory.read_profil_markdown()
    assert contenu.startswith("# Profil (informations libres)")
    assert "## 2026-09-27" in contenu
    assert "Objectif : 70.3 en mai 2027." in contenu


def test_append_profil_note_ajoute_sans_ecraser():
    user_memory.append_profil_note("Premiere note.", quand=date(2026, 9, 27))
    user_memory.append_profil_note("Deuxieme note.", quand=date(2026, 10, 3))
    contenu = user_memory.read_profil_markdown()
    assert "Premiere note." in contenu
    assert "Deuxieme note." in contenu
    assert "## 2026-09-27" in contenu
    assert "## 2026-10-03" in contenu


def test_append_conversation_summary_tague_par_page():
    user_memory.append_conversation_summary(
        "Discussion sur le TSB negatif.", page="charge", quand=date(2026, 9, 27)
    )
    contenu = user_memory.read_conversations_markdown()
    assert "## 2026-09-27 (page: charge)" in contenu
    assert "Discussion sur le TSB negatif." in contenu


def test_charger_contexte_utilisateur_fusionne_profil_et_markdown(monkeypatch):
    profil_fake = Profil(fc_max=190, fc_repos=55, poids_kg=70.0)
    monkeypatch.setattr(user_memory, "load_profil", lambda: profil_fake)
    user_memory.append_profil_note("Contrainte : 6h/semaine max.", quand=date(2026, 9, 27))

    ctx = user_memory.charger_contexte_utilisateur()

    assert ctx.profil_numerique == profil_fake
    assert "Contrainte : 6h/semaine max." in ctx.profil_libre_md
    assert ctx.historique_conversations_md.startswith("# Resume des echanges passes")
