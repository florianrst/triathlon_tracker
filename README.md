# Suivi Triathlon — prepa 70.3 / XL

App locale Python pour suivre une preparation longue (~1 an) vers un
Half-Ironman (70.3) ou un triathlon XL. Ingestion des seances Suunto
(FIT / GPX) + donnees passives 24/7 (NDJSON), suivi de charge polarise 80/20,
historique des seuils / zones, plan de preparation.

## Stack

Streamlit · SQLAlchemy 2 (SQLite -> Postgres) · `fitparse` · `gpxpy` ·
pandas · plotly · folium. Dependances gerees avec **uv**.

## Installation

```bash
uv sync                 # cree .venv et installe tout
```

## Lancer l'app

```bash
uv run streamlit run webapp/app.py
# ou en arriere-plan :
./start.sh   # puis ./stop.sh pour arreter
```

La base SQLite est creee automatiquement dans `data/triathlon.db`.
Pour pointer sur une autre base (ex. Postgres en deploiement) :

```bash
export TRIATHLON_DB_URL="postgresql+psycopg://user:pwd@host/db"
```

## Import des seances

Trois voies (page **Import**) :

1. **Upload manuel** : drag & drop de fichiers `.fit` / `.gpx` / `.ndjson`
   (depose le FIT et le GPX d'une meme seance ensemble pour qu'ils soient
   fusionnes, cf. section suivante).
2. **Dossier surveille** : deposer les fichiers dans `data/incoming/` puis
   cliquer *Scanner le dossier* — ou en CLI :
   ```bash
   uv run python -m ingestion.watcher
   ```
   Le scan ne parcourt que des sous-dossiers `workouts/` (FIT+GPX),
   `activity/` (NDJSON 24/7), `sleep/` et `recovery/` (NDJSON) s'il en trouve
   dans l'arborescence deposee (export Suunto complet), sinon il retombe
   sur un scan a plat de `data/incoming/`.
   Le dedoublonnage se fait en base (nom de fichier / cle de seance) :
   relancer un scan est toujours sans risque.
3. **Saisie manuelle** : formulaire pour une seance sans fichier.

### Import initial d'un gros export Suunto

Pour un export complet (des centaines de seances, plusieurs formats) :

```bash
uv run python -m ingestion.watcher     # import complet, peut prendre plusieurs minutes
```

Une fois le contenu verifie dans l'app (pages Seances / Charge), on peut
archiver les fichiers sources en compresse pour liberer de la place :

```bash
uv run python scripts/archive_incoming.py --dry-run   # apercu, rien n'est modifie
uv run python scripts/archive_incoming.py --yes        # ecrit data/archive/AAAA-MM.tar.gz
                                                        # par mois, verifie, puis supprime les originaux
```
Seuls les dossiers `workouts/` et `activity/` sont archives ; `sleep/` et
`recovery/` sont importes mais pas archives ; le reste (`routes/`,
`comments/`, `reactions/`, `user/`) n'est ni importe ni archive.

### Reclassement des seances & recalcul de charge

Apres une evolution de la logique de classification (sous-types marche / rando
/ vtt / home_trainer...) ou une saisie de seuils :

```bash
uv run python -m scripts.reclassify_sports --dry-run   # apercu, puis --yes
uv run python -m scripts.recompute_tss     --dry-run   # apercu, puis --yes
```

`reclassify_sports` recalcule `sport`/`sous_type` des seances existantes depuis
leur nom de fichier (sans re-import). `recompute_tss` (re)calcule `tss_calc` /
`tss_methode` — la charge d'entrainement calculee **en interne** (module
`core/tss.py`), independante de la montre.

### Fusion FIT + GPX

Sur les montres Suunto testees, le contenu point-par-point d'un FIT est
souvent plus pauvre que celui du GPX correspondant (pas de position, parfois
pas de FC), alors que le resume `session` du FIT est plus riche (FC moy/max,
SWOLF, `recovery_time`, `peak_epoc`, `training_stress_score`). Quand les deux
fichiers d'une meme seance sont presents, l'app les **fusionne** plutot que
de choisir arbitrairement l'un des deux : trace du GPX, synthese et
metriques derivees du FIT. Voir `ingestion/common.py::merge_normalized`.

## Pages

Toutes les vues temporelles utilisent un **selecteur de periode** commun
(`ui/periode.py`) : echelle semaine / mois / annee + granularite de
regroupement (jour / semaine / mois selon l'echelle) + navigation `◀ ▶`.

| Page | Contenu |
|------|---------|
| Accueil (`webapp/app.py`) | KPI globaux, volume par sport, TSS hebdo, polarisation |
| 1 · Import | upload / dossier surveille (FIT/GPX + NDJSON 24-7 / sommeil / recup) / saisie manuelle |
| 2 · Seances | vue agregee par periode + liste filtrable + detail (carte GPS, courbes), edition RPE & notes |
| 3 · Charge | volume par sport, **TSS calcule maison** + PMC (CTL / ATL / TSB), 80/20, bloc recuperation, evolution des zones |
| 4 · Tests & zones | tests de seuil (rattachables a une seance), **profil / seuils historises** (FC seuil, allure seuil, FTP), sets de zones **dates et jamais ecrases** |
| 5 · Plan | generation d'un plan periodise 70.3 / XL a partir de la date de course |
| 6 · Recuperation | sommeil (duree, profond, qualite), balance de recup / stress, charge vs recup J+1 |

## Donnees sources — notes

- **GPX** : source la plus fiable pour le detail seance (lat/lon/alt/time +
  `gpxtpx:hr` en bpm).
- **FIT** : memes infos + quelques metriques derivees ; parsing via `fitparse`,
  volontairement non exhaustif.
- **NDJSON** (passif 24/7, sommeil, recup) : le champ `hr` / `hrAvg` / `hrMin`
  **n'est pas un bpm** mais un indice/ratio Suunto non calibre. On stocke le
  brut agrege. Le fichier sommeil de certains mois **duplique chaque segment**
  — dedup sur `(timestamp, duree)` dans `parse_sleep`. Un segment de sommeil
  du soir (>= 18 h) est rattache au jour de reveil (lendemain).

## Calcul de charge (TSS) — module `core/tss.py`

Cascade hybride par sport, calee sur une echelle 100 = 1 h au seuil :

| sport | methode preferee | fallback |
|-------|------------------|----------|
| natation | `sTSS` (allure /100m vs seuil) | `hrTSS`, `sRPE` |
| velo | `pTSS` (puissance) | `hrTSS`, `sRPE` |
| course | `rTSS` (allure vs allure seuil) | `hrTSS`, `sRPE` |
| renfo / autre | `hrTSS` | `sRPE` |

`hrTSS` = TRIMP de Banister pondere par la reserve cardiaque. Les seuils
proviennent de la table `athlete_thresholds` (historisee, saisie page
Tests & zones) ; a defaut, du profil (`athlete/profil.py`, lu depuis
`user/user.json` sinon FC max 200 / repos 60, seuil ≈ 90 % FCmax). La colonne
`tss_methode` trace la methode retenue pour chaque seance.

## Tests

```bash
uv run pytest
```

Deposer de vrais fichiers dans `data/incoming/` fait passer les tests de
`tests/test_real_files.py` de *skipped* a *passed* (validation des parseurs
sur donnees reelles).

## Modele de donnees

`sessions` (commun, + `recovery_time_s`/`peak_epoc`/`training_stress_score`
montre + `tss_calc`/`tss_methode` calcules maison) + `session_points` (detail
1 Hz, toutes seances, + `puissance`) + `swim_details` / `bike_details` /
`run_details` (1-1 par sport) + `threshold_tests` (+ `session_id` optionnel) et
`zone_sets` et `athlete_thresholds` (historises, jamais ecrases) +
`daily_passive` / `sleep_daily` / `recovery_daily` (agregats journaliers
NDJSON). Voir `core/models.py`.

Pas d'Alembic : `init_db()` cree les tables manquantes et ajoute les colonnes
recentes via un petit `ALTER TABLE` idempotent (`core/database.py`).

## Licence

MIT — voir [`LICENSE`](LICENSE).
