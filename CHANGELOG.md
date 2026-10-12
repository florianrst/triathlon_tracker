# Changelog

Suivi des changements structurels/notables (architecture, packaging, scripts
d'exploitation). Les bugfix et features courants restent dans l'historique git ;
ce fichier ne consigne que les décisions qui changent la façon de lancer, tester ou
organiser le projet.

## 2026-10-12 — Paquet installable (suppression des hacks `sys.path`)

**Pourquoi** : après le split en `webapp/`/`core/`/`athlete/` (entrée précédente),
`webapp/app.py` devait recourir à un `sys.path.insert` manuel pour importer
`core.*` — Streamlit n'ajoute au `sys.path` que le dossier du script lancé, pas la
racine du repo. En vue d'un déploiement en service (Docker, systemd, Streamlit
Cloud...), ce hack est fragile : il ne protège que les lancements qui passent par
`start.sh`.

**Changement** : `pyproject.toml` déclare désormais un `[build-system]` (hatchling)
avec `packages = ["core", "athlete", "ui", "ingestion"]`. `uv sync` installe le
projet lui-même en editable dans `.venv`, rendant ces paquets importables depuis
n'importe quel process/cwd sans manipulation de `sys.path`.

**Fichiers clés** : `pyproject.toml`, `webapp/app.py` (suppression du bloc
`sys.path.insert`), `tests/conftest.py` (suppression du même hack, devenu redondant).

## 2026-10-12 — Réorganisation de la structure du projet

**Pourquoi** : la racine du repo accumulait 9 modules Python à plat
(`app.py`, `database.py`, `models.py`, `analysis.py`, `athlete.py`, `thresholds.py`,
`training_plan.py`, `tss.py`, `user_memory.py`) en plus des dossiers existants —
difficile à scanner visuellement.

**Changement** : regroupement par rôle en trois paquets :
- `webapp/` — présentation Streamlit (`app.py` + `pages/`, siblings obligatoires
  pour le routage multipage de Streamlit).
- `core/` — infra (DB, modèles) + logique générique sans état propre à un athlète
  (`database.py`, `models.py`, `analysis.py`, `training_plan.py`, `thresholds.py`,
  `tss.py`).
- `athlete/` — données/profil propres à l'utilisateur (`profil.py` ex `athlete.py`,
  `memory.py` ex `user_memory.py`).

`ingestion/`, `ui/`, `scripts/`, `tests/`, `data/` restent à leur emplacement actuel.
Ajout de `start.sh` / `stop.sh` à la racine pour lancer/arrêter l'app en arrière-plan
(avec ouverture automatique du navigateur dans `start.sh`).

**Fichiers clés** : tous les imports top-level réécrits avec le préfixe de paquet
(`from core.database import ...`, `from athlete.profil import ...`, etc.), y compris
deux imports différés (`core/database.py` → `core.models.Base`,
`ingestion/persist.py` → `core.thresholds`/`core.tss`). `core/database.py::BASE_DIR`
ajusté pour continuer à résoudre `data/` à la racine du repo.
