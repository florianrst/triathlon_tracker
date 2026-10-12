"""Point d'entree Streamlit - Suivi triathlon (prepa 70.3 / XL).

Lancement ::

    uv run streamlit run webapp/app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.analysis import polarization_ratio, sessions_dataframe
from core.database import init_db
from ui.chat import widget_chat

st.set_page_config(page_title="Suivi Triathlon", page_icon="🏊", layout="wide")

init_db()

st.title("🏊‍♂️🚴‍♂️🏃‍♂️ Suivi Triathlon — prepa 70.3 / XL")
st.caption(
    "Objectif : Half-Ironman (70.3) ou triathlon XL sur ~1 an. "
    "Cadre d'entrainement : polarise 80/20."
)

df = sessions_dataframe()

if df.empty:
    st.info(
        "Aucune seance en base. Va sur la page **Import** pour deposer des "
        "fichiers FIT / GPX, ou pour les placer dans `data/incoming/`."
    )
    st.stop()

# --- KPI globaux ---------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Seances", len(df))
c2.metric("Volume total", f"{df['duree_h'].sum():.1f} h")
periode_j = (df["date"].max() - df["date"].min()).days or 1
c3.metric("Volume / semaine", f"{df['duree_h'].sum() / periode_j * 7:.1f} h")
bas, haut = polarization_ratio(df)
c4.metric("Polarisation (bas / haut)", f"{bas:.0f} / {haut:.0f} %", help="Cible 80 / 20")

# --- Repartition par sport ---------------------------------------------------
left, right = st.columns(2)
with left:
    st.subheader("Volume par sport")
    par_sport = df.groupby("sport")["duree_h"].sum().sort_values(ascending=False)
    st.bar_chart(par_sport)
with right:
    st.subheader("TSS hebdomadaire (calcul maison)")
    hebdo = df.groupby("semaine")["tss"].sum()
    st.bar_chart(hebdo)

# --- Dernieres seances -----------------------------------------------------
st.subheader("Dernieres seances")
cols = ["date", "sport", "sous_type", "duree_h", "distance_m", "hr_moy", "intensite", "ressenti_rpe"]
recent = df.sort_values("date", ascending=False).head(15)[cols].copy()
recent["duree_h"] = recent["duree_h"].round(2)
st.dataframe(recent, use_container_width=True, hide_index=True)

if haut > 25:
    st.warning(
        f"Part haute intensite a {haut:.0f} % sur la periode (cible ~20 %). "
        "Attention a ne pas deriver du modele polarise."
    )

contexte_page = (
    f"Page d'accueil. {len(df)} seances en base, volume total {df['duree_h'].sum():.1f} h, "
    f"volume/semaine {df['duree_h'].sum() / periode_j * 7:.1f} h, "
    f"polarisation {bas:.0f}/{haut:.0f} % (cible 80/20)."
)
widget_chat("accueil", contexte_page)
