# CLAUDE.md — contexte projet

App Streamlit locale de suivi d'une prépa triathlon longue (~1 an) vers un 70.3 / XL.
Le `README.md` est la doc utilisateur ; ce fichier cible le travail sur le code.

## Stack & commandes

- **uv** gère l'environnement. Le projet est un **paquet installable** (`pyproject.toml`
  avec `[build-system]` hatchling, `packages = ["core", "athlete", "ui", "ingestion"]`) :
  `uv sync` installe aussi `triathlon-tracker` lui-même en editable dans `.venv`, donc
  `core`/`athlete`/`ui`/`ingestion` sont importables depuis n'importe où (aucun
  `sys.path.insert` dans le code — nécessaire car Streamlit n'ajoute au `sys.path` que
  le dossier du script lancé, pas la racine du repo).
  - lancer : `uv run streamlit run webapp/app.py` (ou `./start.sh` / `./stop.sh` en arrière-plan)
  - tests : `uv run pytest` (102 tests ; `-p no:warnings` pour le bruit `fitparse`)
- Python ≥ 3.12. Streamlit · SQLAlchemy 2 · pandas · plotly · folium · `fitparse` · `gpxpy`.
- DB : SQLite `data/triathlon.db` par défaut, `TRIATHLON_DB_URL` pour pointer ailleurs.
  **Pas d'Alembic** : `core/database.py::init_db()` fait `create_all` + un bloc `ALTER TABLE …
  ADD COLUMN` idempotent (`_ADDED_COLUMNS`) pour les colonnes ajoutées après coup.
- **Suivi des changements structurels** : voir `CHANGELOG.md` à la racine — une entrée
  par changement notable d'architecture/packaging (pas pour les bugfix/features
  courants, qui restent dans l'historique git).

## Architecture

Racine allégée : seuls `start.sh` / `stop.sh`, la config (`pyproject.toml`, `uv.lock`,
`requirements.txt`), la doc et `data/` restent au niveau racine. Le code est réparti en
trois paquets selon son rôle :
- `webapp/` — présentation Streamlit (`app.py` + `pages/`, doivent rester siblings pour
  le routage multipage de Streamlit).
- `core/` — infra (DB, modèles) et logique générique sans état propre à un athlète.
- `athlete/` — données/profil propres à l'utilisateur (profil physio, notes libres).

```
webapp/
  app.py                  accueil (KPI globaux)
  pages/1_import.py       upload / scan dossier / saisie manuelle
  pages/2_seances.py      vue agrégée par période + liste + détail séance
                          (courbes au choix : FC/allure/vitesse/cadence/puissance/altitude)
  pages/3_charge.py       TSS maison + PMC (CTL/ATL/TSB) + 80/20 + récup + zones
                          (bar plot par sport : volume/distance/TSS/séances au choix)
  pages/4_tests_zones.py  tests de seuil (rattachables à une séance) + profil/seuils + zones
  pages/5_plan.py         générateur de plan périodisé (non persisté)
  pages/6_recuperation.py sommeil + balance récup/stress + charge vs récup J+1

core/
  database.py       engine/session SQLAlchemy, init_db(), chemins data/ (BASE_DIR relatif
                     au repo, pas à core/)
  models.py         ORM : Session, SessionPoint, swim/bike/run_details, threshold_tests,
                     zone_sets, athlete_thresholds, daily_passive/sleep_daily/recovery_daily
  analysis.py        sessions_dataframe, aggregate(df, granularite), periodic_load,
                     load_by_sport(df, granularite, valeur),
                     weekly_load (wrapper), performance_management (PMC), polarization_ratio
  tss.py             hr_tss / r_tss / s_tss / p_tss / s_rpe + routeur compute_tss
  thresholds.py      ThresholdResolver.seuils_for(sport, date) -> tss.Seuils (reste dans
                     core/ même s'il dépend du profil athlète en fallback — c'est avant
                     tout un resolver sur les données DB `athlete_thresholds`)
  training_plan.py   helpers blocs structurés (types, zones cibles, durée totale)

athlete/
  profil.py          Profil (fc_max/repos/poids) lu depuis user/user.json sinon défauts
  memory.py          notes profil libres + résumés de conversation (markdown, jamais écrasé)

ingestion/
  common.py        mappings sport/sous_type, sport_from_filename, merge_normalized
  parse_fit.py     FIT -> dict normalisé (fitparse)
  parse_gpx.py     GPX -> dict normalisé (gpxpy)
  parse_ndjson.py  NDJSON 24/7 -> daily_passive
  parse_sleep.py   NDJSON sommeil -> sleep_daily
  parse_recovery.py NDJSON récup -> recovery_daily
  persist.py       insertion + dispatch + calcul TSS inline
  watcher.py       scan de data/incoming/ (workouts/ activity/ sleep/ recovery/)
  seed.py          données de calibrage initiales

ui/periode.py       selecteur_periode() : semaine/mois/année + granularité + nav ◀▶

scripts/
  archive_incoming.py    archive compressée par mois de l'export importé
  reclassify_sports.py   recalcule sport/sous_type des séances existantes (--dry-run/--yes)
  recompute_tss.py       (re)calcule tss_calc/tss_methode en masse (--dry-run/--yes)
```

## Modèle de données (`core/models.py`)

- `sessions` — commun. Colonnes montre : `recovery_time_s`, `peak_epoc`,
  `training_stress_score`. Colonnes **calculées maison** : `tss_calc`, `tss_methode`
  (`'hrTSS'|'rTSS'|'sTSS'|'pTSS'|'sRPE'`).
- `session_points` — détail 1 Hz toutes séances (+ `puissance`).
- `swim_details` / `bike_details` / `run_details` — 1-1 par sport.
- `threshold_tests` (+ `session_id` optionnel), `zone_sets`, `athlete_thresholds`
  — **historisés, jamais écrasés** : une ligne datée par recalcul.
- `daily_passive` / `sleep_daily` / `recovery_daily` — agrégats journaliers NDJSON.
- Enums : `Sport` (natation/velo/course/renfo/autre), `SourceFormat`, `Discipline`
  (natation/velo/course — "course" couvre marche/rando/trail/tapis).

## Conventions & partis pris

- **On date, on historise.** Jamais d'UPDATE destructif sur tests / zones / seuils.
- **Modèle polarisé 80/20** : `analysis.classify_intensity` (RPE prioritaire, sinon HR),
  cible ~80 % endurance fondamentale.
- **Fusion FIT + GPX** d'une même séance (`merge_normalized`) : trace du GPX, synthèse et
  métriques dérivées du FIT. Dédup en base sur `source_file` / `source_key`.
- **Classification** : `sport_from_filename` (token après le dernier `-` du nom de fichier
  Suunto `YYYY-MM-DD_HH.MM.SS-<token>.fit`) est prioritaire sur le contenu FIT/GPX.
- **TSS** : cascade par sport calée 100 = 1 h au seuil. Seuils depuis `athlete_thresholds`
  valides à la date, sinon profil (FC max 200 / repos 60, seuil ≈ 0.9·FCmax). Relancer
  `scripts/recompute_tss --yes` après toute saisie de seuils.
- **Toutes les vues temporelles** passent par `ui/periode.selecteur_periode` (clé de
  `session_state` distincte par page).
- Graphes en **plotly** dans `webapp/pages/` ; `st.bar_chart` seulement dans `webapp/app.py`.
- Lectures : `pd.read_sql(select(Model)…, engine)`. Écritures : `with get_session() as db:`.

## Données sources — pièges (montre **Suunto**)

- `hr` / `hrAvg` / `hrMin` des NDJSON = **ratio Suunto non calibré (~0.5–1.2), pas des bpm**.
- `sleep/2026-08.ndjson` **duplique chaque segment** → dédup `(timestamp, duree)` dans
  `parse_sleep`. Un segment de sommeil du soir (≥ 18 h) est rattaché au **lendemain**
  (jour de réveil).
- Sous-dossiers ignorés par le watcher : `routes/`, `comments/`, `reactions/`, `user/`.

## Tests

`tests/conftest.py` bascule `TRIATHLON_DB_URL` sur une SQLite temp + fixture `_fresh_db`
(drop/create par test). `tests/test_real_files.py` ne tourne que si de vrais fichiers sont
dans `data/incoming/`. Pas de tests sur les pages Streamlit (validation via
`streamlit.testing.v1.AppTest` en ad hoc si besoin).
