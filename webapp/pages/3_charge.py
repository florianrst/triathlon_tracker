"""Page Charge : TSS calcule maison (PMC), respect du 80/20, sommeil & recup."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import select

from core.analysis import (
    INTENSITES,
    aggregate,
    load_by_sport,
    performance_management,
    periodic_load,
    polarization_ratio,
    sessions_dataframe,
    zone_history,
)
from core.database import engine, init_db
from core.models import RecoveryDaily, SleepDaily
from ui.chat import widget_chat
from ui.periode import selecteur_periode

st.set_page_config(page_title="Charge", page_icon="📈", layout="wide")
init_db()

st.title("📈 Charge d'entrainement & polarisation")

df_all = sessions_dataframe()
if df_all.empty:
    st.info("Aucune seance. Va sur la page Import.")
    st.stop()

periode = selecteur_periode("charge")
mask = (df_all["date"] >= periode.debut) & (df_all["date"] <= periode.fin)
df = df_all[mask].copy()
if df.empty:
    st.warning(f"Aucune seance sur {periode.libelle().lower()}.")
    st.stop()

pl = periodic_load(df, periode.granularite)

# --- Volume par sport ----------------------------------------------------
METRIQUES = {
    "Volume (h)": ("duree_h", "h", "{:.1f}"),
    "Distance (km)": ("distance_km", "km", "{:.0f}"),
    "TSS": ("tss", "TSS", "{:.0f}"),
    "Seances": ("n_seances", "seances", "{:.0f}"),
}
st.subheader(f"Charge par sport — groupe par {periode.granularite}")
choix = st.radio("Afficher", list(METRIQUES), horizontal=True, key="charge_metrique")
col, unite, fmt = METRIQUES[choix]
lb = load_by_sport(df, periode.granularite, col)
sports = [c for c in ["natation", "velo", "course", "renfo", "autre"] if c in lb.columns]
totaux = lb[sports].sum(axis=1)
seuil = 0.05 * totaux.max() if len(totaux) else 0
fig = go.Figure()
for sp in sports:
    vals = lb[sp]
    fig.add_bar(
        x=lb["bucket"], y=vals, name=sp,
        text=[fmt.format(v) if v >= seuil and v > 0 else "" for v in vals],
        textposition="inside", insidetextanchor="middle",
    )
fig.add_scatter(
    x=lb["bucket"], y=totaux, mode="text", showlegend=False, hoverinfo="skip",
    text=[fmt.format(v) for v in totaux], textposition="top center",
)
fig.update_layout(
    barmode="stack", height=380, yaxis_title=unite, margin=dict(t=50),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
)
fig.update_yaxes(range=[0, totaux.max() * 1.15] if len(totaux) and totaux.max() > 0 else None)
st.plotly_chart(fig, use_container_width=True)

# --- TSS calcule maison + PMC (CTL / ATL / TSB) -------------------------
st.subheader("Charge (TSS calcule maison) — CTL / ATL / TSB")
st.caption(
    "TSS calcule EN INTERNE a partir des donnees brutes (FC, allure, puissance) "
    "— independant de la montre. CTL = forme (42 j), ATL = fatigue (7 j), "
    "TSB = fraicheur (CTL − ATL)."
)
pmc_all = performance_management(df_all)  # PMC sur tout l'historique, on zoome ensuite
pmc = pmc_all[(pmc_all["date"] >= pd.Timestamp(periode.debut)) & (pmc_all["date"] <= pd.Timestamp(periode.fin))]
fig2 = go.Figure()
fig2.add_bar(x=pmc["date"], y=pmc["tss_jour"], name="TSS / jour", marker_color="#d7dde3")
fig2.add_scatter(x=pmc["date"], y=pmc["ctl"], name="CTL (forme)", line=dict(color="#2f6fed"))
fig2.add_scatter(x=pmc["date"], y=pmc["atl"], name="ATL (fatigue)", line=dict(color="#e2483d"))
fig2.add_scatter(x=pmc["date"], y=pmc["tsb"], name="TSB (fraicheur)",
                 line=dict(color="#4c9a52", dash="dot"))
fig2.update_layout(height=360, margin=dict(t=50),
                   legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
st.plotly_chart(fig2, use_container_width=True)

meth = df["tss_methode"].dropna().value_counts()
if not meth.empty:
    total = int(meth.sum())
    txt = " · ".join(f"{k} {100 * v / total:.0f} %" for k, v in meth.items())
    st.caption(f"Methodes de calcul sur la periode : {txt}")

# --- Respect du 80/20 --------------------------------------------------
st.subheader("Respect du modele polarise 80/20")
bas, haut = polarization_ratio(df)
g1, g2 = st.columns([1, 2])
with g1:
    gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=haut,
        title={"text": "% haute intensite"},
        gauge={
            "axis": {"range": [0, 40]},
            "bar": {"color": "#e2483d"},
            "steps": [
                {"range": [0, 20], "color": "#cdeccd"},
                {"range": [20, 30], "color": "#fdf1c2"},
                {"range": [30, 40], "color": "#f7d2ce"},
            ],
            "threshold": {"line": {"color": "black", "width": 3}, "value": 20},
        },
    ))
    gauge.update_layout(height=280, margin=dict(t=50, b=10))
    st.plotly_chart(gauge, use_container_width=True)
    st.metric("Endurance fondamentale", f"{bas:.0f} %", help="Cible ~80 %")

with g2:
    parts = pl[["bucket", "basse", "moderee", "haute"]].copy()
    long = parts.melt("bucket", var_name="intensite", value_name="heures")
    order = {k: i for i, k in enumerate(INTENSITES)}
    long = long.sort_values("intensite", key=lambda s: s.map(order))
    figp = px.bar(long, x="bucket", y="heures", color="intensite",
                  color_discrete_map={"basse": "#4c9a52", "moderee": "#e8b84b", "haute": "#e2483d"})
    figp.update_layout(barmode="stack", height=280, margin=dict(t=50),
                       legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    st.plotly_chart(figp, use_container_width=True)

recap = pl[["bucket", "total_h", "tss", "pct_basse", "pct_haute"]].copy()
recap[["total_h", "tss", "pct_basse", "pct_haute"]] = recap[
    ["total_h", "tss", "pct_basse", "pct_haute"]
].round(1)
st.dataframe(recap, use_container_width=True, hide_index=True)

# --- Recuperation (sommeil + stress) ----------------------------------
st.divider()
st.subheader("Recuperation sur la periode")
sleep = pd.read_sql(
    select(SleepDaily).where(
        SleepDaily.date >= periode.debut, SleepDaily.date <= periode.fin
    ),
    engine,
)
recov = pd.read_sql(
    select(RecoveryDaily).where(
        RecoveryDaily.date >= periode.debut, RecoveryDaily.date <= periode.fin
    ),
    engine,
)
r1, r2, r3 = st.columns(3)
if not sleep.empty:
    h_moy = sleep["duree_totale_s"].dropna().mean() / 3600.0
    pct_court = (sleep["duree_totale_s"].dropna() < 7 * 3600).mean() * 100
    r1.metric("Sommeil moyen / nuit", f"{h_moy:.1f} h")
    r2.metric("Nuits < 7 h", f"{pct_court:.0f} %")
else:
    r1.info("Pas de donnees de sommeil sur la periode.")
if not recov.empty:
    r3.metric("Balance recup moyenne", f"{recov['balance_moy'].dropna().mean():.2f}",
              help="0 → 1, plus haut = mieux recupere")
st.caption("Detail complet : page **Recuperation**.")

# --- Evolution des zones --------------------------------------------
st.divider()
st.subheader("Evolution des seuils / zones")
disc = st.selectbox("Discipline", ["course", "natation", "velo"])
zh = zone_history(disc)
if zh.empty:
    st.info("Aucun set de zones pour cette discipline. Voir la page Tests & zones.")
else:
    for _, z in zh.iterrows():
        with st.expander(f"Valide a partir du {z['date_debut_validite']}"):
            st.json(z["zones_json"])

if not pmc.empty:
    derniere = pmc.iloc[-1]
    pmc_txt = f"CTL/ATL/TSB (derniere valeur) : {derniere['ctl']:.0f} / {derniere['atl']:.0f} / {derniere['tsb']:.0f}."
else:
    pmc_txt = "Pas de PMC calculable sur la periode."
contexte_page = (
    f"Page Charge, periode {periode.libelle()}. "
    f"Polarisation {bas:.0f}/{haut:.0f} % (cible 80/20). {pmc_txt} "
    f"Charge periodique (dernieres lignes) :\n{pl.tail(3).to_string(index=False)}"
)
widget_chat("charge", contexte_page)
