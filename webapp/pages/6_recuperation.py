"""Page Recuperation : sommeil + balance de recuperation / stress.

Donnees issues de l'export Suunto (dossiers ``sleep/`` et ``recovery/``),
agregees par jour. Rappel : ``hr_nuit_*`` est un ratio Suunto non calibre,
pas des bpm.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from sqlalchemy import select

from core.analysis import performance_management, sessions_dataframe
from core.database import engine, init_db
from core.models import RecoveryDaily, SleepDaily
from ui.chat import widget_chat
from ui.periode import selecteur_periode

st.set_page_config(page_title="Recuperation", page_icon="😴", layout="wide")
init_db()

st.title("😴 Sommeil & recuperation")

sleep_all = pd.read_sql(select(SleepDaily).order_by(SleepDaily.date), engine)
recov_all = pd.read_sql(select(RecoveryDaily).order_by(RecoveryDaily.date), engine)
if sleep_all.empty and recov_all.empty:
    st.info(
        "Aucune donnee de sommeil / recuperation. Depose l'export Suunto "
        "(dossiers `sleep/` et `recovery/`) puis lance un scan sur la page Import."
    )
    st.stop()

periode = selecteur_periode("recup")


def _slice(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["date"] >= periode.debut) & (df["date"] <= periode.fin)].copy()


sleep = _slice(sleep_all)
recov = _slice(recov_all)

# --- Sommeil ---------------------------------------------------------
st.subheader("Sommeil")
if sleep.empty:
    st.caption("Pas de donnees de sommeil sur cette periode.")
else:
    sleep["h_totale"] = sleep["duree_totale_s"] / 3600.0
    sleep["h_profond"] = sleep["sommeil_profond_s"].fillna(0) / 3600.0
    sleep["h_leger"] = (sleep["h_totale"] - sleep["h_profond"]).clip(lower=0)
    sleep["moy_7j"] = sleep["h_totale"].rolling(7, min_periods=1).mean()

    k1, k2, k3 = st.columns(3)
    k1.metric("Duree moyenne / nuit", f"{sleep['h_totale'].mean():.1f} h")
    k2.metric("Nuits < 7 h", f"{(sleep['h_totale'] < 7).mean() * 100:.0f} %")
    if sleep["qualite"].notna().any():
        k3.metric("Qualite moyenne", f"{sleep['qualite'].mean() * 100:.0f} / 100")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(x=sleep["date"], y=sleep["h_profond"], name="Profond", marker_color="#2f6fed")
    fig.add_bar(x=sleep["date"], y=sleep["h_leger"], name="Leger", marker_color="#a9c6f5")
    fig.add_scatter(x=sleep["date"], y=sleep["moy_7j"], name="Moyenne 7 j",
                    line=dict(color="#1f2937"))
    if sleep["qualite"].notna().any():
        fig.add_scatter(x=sleep["date"], y=sleep["qualite"] * 100, name="Qualite",
                        line=dict(color="#e8b84b", dash="dot"), secondary_y=True)
        fig.update_yaxes(title_text="Qualite (/100)", secondary_y=True, range=[0, 100])
    fig.update_layout(barmode="stack", height=380, legend=dict(orientation="h"),
                      yaxis_title="heures")
    st.plotly_chart(fig, use_container_width=True)

# --- Recuperation / stress -----------------------------------------
st.subheader("Balance de recuperation & stress")
if recov.empty:
    st.caption("Pas de donnees de recuperation sur cette periode.")
else:
    recov["moy_7j"] = recov["balance_moy"].rolling(7, min_periods=1).mean()
    k1, k2 = st.columns(2)
    k1.metric("Balance moyenne", f"{recov['balance_moy'].mean():.2f}",
              help="0 → 1, plus haut = mieux recupere")
    if recov["pct_stress_eleve"].notna().any():
        k2.metric("Temps en stress eleve", f"{recov['pct_stress_eleve'].mean() * 100:.0f} %")

    fig2 = go.Figure()
    fig2.add_scatter(x=recov["date"], y=recov["balance_moy"], name="Balance (moy jour)",
                     line=dict(color="#4c9a52"))
    fig2.add_scatter(x=recov["date"], y=recov["balance_min"], name="Balance (min jour)",
                     line=dict(color="#4c9a52", dash="dot"))
    if recov["pct_stress_eleve"].notna().any():
        fig2.add_bar(x=recov["date"], y=recov["pct_stress_eleve"], name="Part stress eleve",
                     marker_color="#f0b8b2", yaxis="y2")
        fig2.update_layout(yaxis2=dict(overlaying="y", side="right", range=[0, 1],
                                       title="part stress eleve"))
    fig2.update_layout(height=360, legend=dict(orientation="h"), yaxis_title="balance")
    st.plotly_chart(fig2, use_container_width=True)

# --- Charge vs recuperation (J+1) --------------------------------
st.divider()
st.subheader("Charge d'entrainement vs recuperation le lendemain")
st.caption("TSS d'un jour (barres) et balance de recup / duree de sommeil du LENDEMAIN.")
sess = sessions_dataframe()
if sess.empty or (sleep.empty and recov.empty):
    st.caption("Pas assez de donnees.")
else:
    pmc = performance_management(sess)
    pmc = pmc[(pmc["date"] >= pd.Timestamp(periode.debut)) & (pmc["date"] <= pd.Timestamp(periode.fin))]
    fig3 = make_subplots(specs=[[{"secondary_y": True}]])
    fig3.add_bar(x=pmc["date"], y=pmc["tss_jour"], name="TSS / jour", marker_color="#d7dde3")
    if not recov.empty:
        r = recov.copy()
        r["date_prev"] = pd.to_datetime(r["date"]) - pd.Timedelta(days=1)
        fig3.add_scatter(x=r["date_prev"], y=r["balance_moy"], name="Balance J+1",
                         line=dict(color="#4c9a52"), secondary_y=True)
        fig3.update_yaxes(title_text="balance J+1", secondary_y=True, range=[0, 1])
    fig3.update_layout(height=340, legend=dict(orientation="h"), yaxis_title="TSS")
    st.plotly_chart(fig3, use_container_width=True)

sommeil_txt = f"{sleep['h_totale'].mean():.1f} h/nuit" if not sleep.empty and "h_totale" in sleep else "n/a"
balance_txt = f"{recov['balance_moy'].mean():.2f}" if not recov.empty else "n/a"
contexte_page = (
    f"Page Recuperation, periode {periode.libelle()}. "
    f"Sommeil moyen : {sommeil_txt}. Balance recup moyenne : {balance_txt}."
)
widget_chat("recuperation", contexte_page)
