"""Page Import : upload manuel + scan du dossier surveille + saisie manuelle."""

from __future__ import annotations

from collections import Counter
from datetime import date

import streamlit as st

from core.database import INCOMING_DIR, init_db
from ingestion.persist import ingest_paths, persist_session
from ingestion.watcher import eligible_paths, scan_incoming
from ui.chat import widget_chat

st.set_page_config(page_title="Import", page_icon="📥", layout="wide")
init_db()

st.title("📥 Import des seances")

_BADGE = {
    "imported": "✅",
    "passive": "📊",
    "duplicate": "⏭️",
    "skipped": "⏭️",
    "error": "❌",
}


def _summary_table(results):
    counts = Counter(r.status for r in results)
    cols = st.columns(len(counts) or 1)
    for col, (status, n) in zip(cols, sorted(counts.items())):
        col.metric(f"{_BADGE.get(status, '•')} {status}", n)
    errors = [r for r in results if r.status == "error"]
    if errors:
        with st.expander(f"{len(errors)} erreur(s) — detail"):
            for r in errors:
                st.write(f"❌ **{r.path}** — {r.detail}")


def _render(results):
    for r in results:
        st.write(f"{_BADGE.get(r.status, '•')} **{r.path}** — {r.status} — {r.detail}")


# --- 1. Upload manuel --------------------------------------------------------
st.header("1. Upload manuel (drag & drop)")
st.caption(
    "FIT / GPX pour les seances (depose les deux fichiers d'une meme seance "
    "ensemble pour qu'ils soient fusionnes), NDJSON / JSONL pour les donnees "
    "passives 24/7."
)
files = st.file_uploader(
    "Fichiers a importer",
    type=["fit", "gpx", "ndjson", "jsonl"],
    accept_multiple_files=True,
)
if files and st.button("Importer les fichiers deposes", type="primary"):
    dests = []
    for f in files:
        dest = INCOMING_DIR / f.name
        dest.write_bytes(f.getbuffer())
        dests.append(dest)
    _render(ingest_paths(dests))

st.divider()

# --- 2. Dossier surveille --------------------------------------------------
st.header("2. Dossier surveille")
st.caption(
    f"Depose des fichiers (ou une arborescence d'export Suunto avec des "
    f"dossiers `workouts/` et `activity/`) dans `{INCOMING_DIR}` puis lance un "
    "scan. Les seances deja importees sont ignorees (dedoublonnage)."
)

eligible = eligible_paths(INCOMING_DIR)
par_ext = Counter(p.suffix.lower() for p in eligible)


def _ndjson_kind(p) -> str:
    parents = {x.name.lower() for x in p.parents}
    if "sleep" in parents:
        return "sommeil"
    if "recovery" in parents:
        return "recup"
    return "24/7"


ndjson_kinds = Counter(
    _ndjson_kind(p) for p in eligible if p.suffix.lower() in (".ndjson", ".jsonl")
)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Fichiers FIT", par_ext.get(".fit", 0))
c2.metric("Fichiers GPX", par_ext.get(".gpx", 0))
c3.metric("NDJSON 24/7", ndjson_kinds.get("24/7", 0))
c4.metric("NDJSON sommeil", ndjson_kinds.get("sommeil", 0))
c5.metric("NDJSON recup", ndjson_kinds.get("recup", 0))

limite = st.number_input(
    "Limiter a N seances/fichiers (essai rapide, 0 = tout)", min_value=0, value=0, step=10
)
if st.button("Scanner le dossier maintenant", type="primary"):
    prog_bar = st.progress(0.0)
    status = st.empty()

    def _on_progress(done: int, total: int, result):
        prog_bar.progress(done / total if total else 1.0)
        status.write(f"{done}/{total} — dernier : {result.path} ({result.status})")

    results = scan_incoming(progress=_on_progress, limit=limite or None)
    prog_bar.empty()
    status.empty()
    if not results:
        st.info("Aucun fichier eligible trouve.")
    else:
        _summary_table(results)

st.divider()

# --- 3. Saisie manuelle -------------------------------------------------
st.header("3. Seance sans fichier (saisie manuelle)")
with st.form("manuel"):
    col1, col2, col3 = st.columns(3)
    d = col1.date_input("Date", value=date.today())
    sport = col2.selectbox("Sport", ["natation", "velo", "course", "renfo", "autre"])
    sous_type = col3.text_input("Sous-type", placeholder="route, piscine, home_trainer…")
    col4, col5, col6 = st.columns(3)
    duree_min = col4.number_input("Duree (min)", min_value=1, value=60)
    distance_km = col5.number_input("Distance (km)", min_value=0.0, value=0.0, step=0.1)
    d_plus = col6.number_input("D+ (m)", min_value=0, value=0)
    col7, col8, col9 = st.columns(3)
    hr_moy = col7.number_input("FC moy", min_value=0, value=0)
    hr_max = col8.number_input("FC max", min_value=0, value=0)
    rpe = col9.slider("Ressenti RPE", 1, 10, 5)
    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Enregistrer la seance", type="primary")

if submitted:
    norm = {
        "date": d,
        "sport": sport,
        "sous_type": sous_type or None,
        "duree_s": int(duree_min * 60),
        "distance_m": distance_km * 1000 or None,
        "d_plus_m": float(d_plus) or None,
        "hr_moy": int(hr_moy) or None,
        "hr_max": int(hr_max) or None,
        "ressenti_rpe": int(rpe),
        "notes": notes or None,
        "source_file": f"manuel-{d.isoformat()}-{sport}-{int(duree_min)}min",
        "source_format": "manuel",
        "points": [],
        "details": {},
    }
    res = persist_session(norm)
    _render([res])

contexte_page = (
    f"Page Import. Dossier surveille : {par_ext.get('.fit', 0)} FIT, "
    f"{par_ext.get('.gpx', 0)} GPX, {ndjson_kinds.get('24/7', 0)} NDJSON 24/7, "
    f"{ndjson_kinds.get('sommeil', 0)} NDJSON sommeil, {ndjson_kinds.get('recup', 0)} NDJSON recup "
    "en attente d'import."
)
widget_chat("import", contexte_page)
