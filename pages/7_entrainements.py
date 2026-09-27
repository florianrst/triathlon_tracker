"""Page Entrainements : bibliotheque de seances planifiees, structurees par
blocs (echauffement / travail / recuperation / retour au calme), proche d'un
"workout" TrainingPeaks. Date prevue optionnelle (sinon simple modele
reutilisable). Une seance planifiee peut etre rattachee a la seance reelle
importee correspondante (planifie vs realise).

Contrairement aux tests de seuil / zones, PAS historise : on peut corriger un
bloc ou reprogrammer une date librement (cf. docstring ``PlannedWorkout``).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import select

from database import engine, get_session, init_db
from models import PlannedWorkout, Session, Sport, StatutSeance, TypeSeance
from training_plan import TYPES_BLOC, ZONES_CIBLES, duree_totale_s, formater_bloc, formater_duree
from ui.chat import widget_chat

st.set_page_config(page_title="Entrainements", page_icon="🏋️", layout="wide")
init_db()

st.title("🏋️ Entrainements — bibliotheque & planning")

# --- 1. Construction d'une nouvelle seance --------------------------------
st.header("Nouvelle seance")

st.session_state.setdefault("nouveaux_blocs", [])

c1, c2, c3 = st.columns(3)
titre = c1.text_input("Titre", placeholder="Seuil 6x3min")
sport = c2.selectbox("Sport", [s.value for s in Sport])
type_seance = c3.selectbox("Type", [t.value for t in TypeSeance])

c4, c5 = st.columns([1, 3])
planifiee = c4.checkbox("Planifier une date")
date_saisie = c5.date_input("Date prevue", value=date.today(), disabled=not planifiee)
date_prevue = date_saisie if planifiee else None

st.subheader("Blocs")
with st.form("ajout_bloc", clear_on_submit=True):
    b1, b2, b3, b4, b5, b6 = st.columns([2, 1, 1, 1, 1, 2])
    b_type = b1.selectbox("Type de bloc", TYPES_BLOC)
    b_min = b2.number_input("min", min_value=0, value=0)
    b_sec = b3.number_input("sec", min_value=0, max_value=59, value=0)
    b_dist = b4.number_input("ou distance (m)", min_value=0, value=0)
    b_rep = b5.number_input("repetitions", min_value=1, value=1)
    b_zone = b6.selectbox("Zone cible", ["—"] + ZONES_CIBLES)
    b_notes = st.text_input("Notes du bloc", placeholder="allure, cadence, materiel...")
    if st.form_submit_button("➕ Ajouter le bloc"):
        duree_s = b_min * 60 + b_sec
        st.session_state["nouveaux_blocs"].append({
            "type": b_type,
            "duree_s": duree_s or None,
            "distance_m": float(b_dist) or None,
            "repetitions": int(b_rep),
            "zone_cible": None if b_zone == "—" else b_zone,
            "notes": b_notes or None,
        })

if st.session_state["nouveaux_blocs"]:
    for i, b in enumerate(st.session_state["nouveaux_blocs"]):
        lc, rc = st.columns([6, 1])
        lc.write(f"{i + 1}. {formater_bloc(b)}")
        if rc.button("🗑️", key=f"del_bloc_{i}"):
            st.session_state["nouveaux_blocs"].pop(i)
            st.rerun()
    st.caption(f"Duree totale estimee : {formater_duree(duree_totale_s(st.session_state['nouveaux_blocs']))}")
else:
    st.caption("Aucun bloc ajoute pour l'instant.")

notes_seance = st.text_area("Notes generales sur la seance")

if st.button("💾 Enregistrer la seance", type="primary", disabled=not titre or not st.session_state["nouveaux_blocs"]):
    blocs = st.session_state["nouveaux_blocs"]
    with get_session() as db:
        db.add(PlannedWorkout(
            titre=titre,
            sport=Sport(sport),
            type_seance=TypeSeance(type_seance),
            date_prevue=date_prevue,
            statut=StatutSeance.prevue,
            blocs_json=blocs,
            duree_estimee_s=duree_totale_s(blocs) or None,
            notes=notes_seance or None,
        ))
    st.session_state["nouveaux_blocs"] = []
    st.success("Seance enregistree.")
    st.rerun()

st.divider()

# --- 2. Bibliotheque / planning --------------------------------------------
st.header("Bibliotheque & planning")

plans = pd.read_sql(select(PlannedWorkout).order_by(PlannedWorkout.created_at.desc()), engine)
if plans.empty:
    st.info("Aucune seance planifiee pour l'instant.")
    widget_chat("entrainements", "Page Entrainements. Aucune seance planifiee pour l'instant.")
    st.stop()

for col in ("sport", "type_seance", "statut"):
    plans[col] = plans[col].map(lambda s: getattr(s, "value", s))

f1, f2, f3 = st.columns(3)
sports_sel = f1.multiselect("Sport", sorted(plans["sport"].unique()), default=list(plans["sport"].unique()))
types_sel = f2.multiselect("Type", sorted(plans["type_seance"].unique()), default=list(plans["type_seance"].unique()))
statuts_sel = f3.multiselect("Statut", sorted(plans["statut"].unique()), default=list(plans["statut"].unique()))

filtre = plans[
    plans["sport"].isin(sports_sel) & plans["type_seance"].isin(types_sel) & plans["statut"].isin(statuts_sel)
].copy()
filtre = filtre.sort_values("date_prevue", ascending=True, na_position="last")

sessions_df = pd.read_sql(
    select(Session.id, Session.date, Session.sport, Session.sous_type, Session.duree_s)
    .order_by(Session.date.desc()),
    engine,
)
if not sessions_df.empty:
    sessions_df["sport"] = sessions_df["sport"].map(lambda s: getattr(s, "value", s))


def _session_label(sid: int) -> str:
    r = sessions_df[sessions_df["id"] == sid].iloc[0]
    st_txt = f"/{r['sous_type']}" if r["sous_type"] else ""
    return f"#{sid} — {r['date']} — {r['sport']}{st_txt} — {r['duree_s'] // 60} min"


if filtre.empty:
    st.caption("Aucune seance ne correspond aux filtres.")
else:
    for _, row in filtre.iterrows():
        date_txt = row["date_prevue"].isoformat() if pd.notna(row["date_prevue"]) else "sans date"
        titre_expander = f"{row['titre']} — {row['sport']} / {row['type_seance']} — {date_txt} — [{row['statut']}]"
        with st.expander(titre_expander):
            for b in row["blocs_json"]:
                st.write(f"- {formater_bloc(b)}")
            if row["duree_estimee_s"]:
                st.caption(f"Duree estimee : {formater_duree(row['duree_estimee_s'])}")
            if row["notes"]:
                st.caption(row["notes"])

            if pd.notna(row["session_id"]):
                st.success(f"Rattachee a la seance reelle {_session_label(int(row['session_id']))}.")
            elif not sessions_df.empty:
                cand = sessions_df[sessions_df["sport"] == row["sport"]]
                choix = st.selectbox(
                    "Rattacher a une seance reelle",
                    [None] + cand["id"].tolist(),
                    format_func=lambda i: "— aucune —" if i is None else _session_label(i),
                    key=f"link_{row['id']}",
                )
                if choix is not None and st.button("Marquer comme realisee", key=f"realise_{row['id']}"):
                    with get_session() as db:
                        obj = db.get(PlannedWorkout, int(row["id"]))
                        obj.session_id = int(choix)
                        obj.statut = StatutSeance.realisee
                    st.success("Seance rattachee et marquee realisee.")
                    st.rerun()

            statut_options = [s.value for s in StatutSeance]
            nouveau_statut = st.selectbox(
                "Statut", statut_options, index=statut_options.index(row["statut"]), key=f"statut_{row['id']}"
            )
            sc1, sc2 = st.columns(2)
            if sc1.button("Mettre a jour le statut", key=f"maj_statut_{row['id']}"):
                with get_session() as db:
                    obj = db.get(PlannedWorkout, int(row["id"]))
                    obj.statut = StatutSeance(nouveau_statut)
                st.success("Statut mis a jour.")
                st.rerun()
            if sc2.button("🗑️ Supprimer", key=f"del_{row['id']}"):
                with get_session() as db:
                    obj = db.get(PlannedWorkout, int(row["id"]))
                    db.delete(obj)
                st.success("Seance supprimee.")
                st.rerun()

a_venir = filtre[
    filtre["date_prevue"].notna()
    & (filtre["date_prevue"] >= date.today())
    & (filtre["date_prevue"] <= date.today() + timedelta(days=7))
]
if not a_venir.empty:
    contexte_page = (
        f"Page Entrainements. {len(a_venir)} seance(s) planifiee(s) dans les 7 prochains jours : "
        + "; ".join(f"{r['date_prevue']} {r['titre']} ({r['sport']}/{r['type_seance']})" for _, r in a_venir.iterrows())
    )
else:
    contexte_page = f"Page Entrainements. {len(plans)} seance(s) dans la bibliotheque, aucune planifiee sous 7 jours."
widget_chat("entrainements", contexte_page)
