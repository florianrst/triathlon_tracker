"""Page Seances : liste filtrable + detail (carte GPS, courbes FC / allure / puissance)."""

from __future__ import annotations

import folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from sqlalchemy import select
from streamlit_folium import st_folium

from core.analysis import aggregate, sessions_dataframe
from core.database import engine, get_session, init_db
from core.models import BikeDetails, RunDetails, Session, SessionPoint, SwimDetails
from ui.chat import widget_chat
from ui.periode import selecteur_periode

st.set_page_config(page_title="Seances", page_icon="📋", layout="wide")
init_db()


def _label(frame: pd.DataFrame, i: int) -> str:
    r = frame[frame["id"] == i].iloc[0]
    return f"#{i} — {r['date']} — {r['sport']} — {r['duree_min']:.0f} min"


def _sport_details(session_id: int, sport: str) -> None:
    model = {"natation": SwimDetails, "velo": BikeDetails, "course": RunDetails}.get(sport)
    if model is None:
        return
    with get_session() as db:
        det = db.get(model, int(session_id))
    if det is None:
        return
    fields = {c.name: getattr(det, c.name) for c in det.__table__.columns if c.name != "session_id"}
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        return
    st.subheader("Metriques specifiques")
    st.columns(1)[0].table(pd.DataFrame(fields.items(), columns=["metrique", "valeur"]))


st.title("📋 Seances")

df = pd.read_sql(select(Session).order_by(Session.date.desc()), engine)
if df.empty:
    st.info("Aucune seance. Va sur la page Import.")
    st.stop()

df["sport"] = df["sport"].map(lambda s: getattr(s, "value", s))
df["duree_min"] = (df["duree_s"] / 60).round(1)
df["distance_km"] = (df["distance_m"] / 1000).round(2)

# --- Vue agregee (par jour / semaine / mois) ---------------------------
st.subheader("Vue agregee")
periode = selecteur_periode("seances")
agg_src = sessions_dataframe()
agg_src = agg_src[(agg_src["date"] >= periode.debut) & (agg_src["date"] <= periode.fin)]
if agg_src.empty:
    st.caption(f"Aucune seance sur {periode.libelle().lower()}.")
else:
    buckets = aggregate(agg_src, periode.granularite, valeurs=("duree_h", "tss"))
    a1, a2, a3 = st.columns(3)
    a1.metric("Seances", int(buckets["n_seances"].sum()))
    a2.metric("Volume", f"{buckets['duree_h'].sum():.1f} h")
    a3.metric("TSS cumule", f"{buckets['tss'].sum():.0f}")
    figb = px.bar(buckets, x="bucket", y=["duree_h", "tss"], barmode="group",
                  labels={"value": "", "bucket": "", "variable": ""})
    figb.update_layout(height=300, margin=dict(t=50),
                       legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    st.plotly_chart(figb, use_container_width=True)

st.divider()

# --- Filtres ---------------------------------------------------------------
c1, c2, c3 = st.columns([2, 2, 3])
sports = c1.multiselect("Sport", sorted(df["sport"].unique()), default=list(df["sport"].unique()))
dmin, dmax = df["date"].min(), df["date"].max()
plage = c2.date_input("Periode", value=(dmin, dmax))
q = c3.text_input("Recherche notes / sous-type")

f = df[df["sport"].isin(sports)]
if isinstance(plage, tuple) and len(plage) == 2:
    f = f[(f["date"] >= plage[0]) & (f["date"] <= plage[1])]
if q:
    ql = q.lower()
    f = f[
        f["notes"].fillna("").str.lower().str.contains(ql)
        | f["sous_type"].fillna("").str.lower().str.contains(ql)
    ]

st.dataframe(
    f[["id", "date", "sport", "sous_type", "duree_min", "distance_km", "hr_moy", "hr_max",
       "ressenti_rpe", "source_format"]],
    use_container_width=True,
    hide_index=True,
)

# --- Detail d'une seance -------------------------------------------------
st.divider()
sid = st.selectbox("Detail de la seance", f["id"].tolist(),
                   format_func=lambda i: _label(f, i))
if sid is None:
    st.stop()

row = df[df["id"] == sid].iloc[0]
pts = pd.read_sql(
    select(SessionPoint).where(SessionPoint.session_id == int(sid)).order_by(SessionPoint.t_offset_s),
    engine,
)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Duree", f"{row['duree_min']:.0f} min")
m2.metric("Distance", f"{row['distance_km']:.2f} km" if pd.notna(row["distance_km"]) else "—")
m3.metric("D+", f"{row['d_plus_m']:.0f} m" if pd.notna(row["d_plus_m"]) else "—")
m4.metric("FC moy", f"{row['hr_moy']:.0f}" if pd.notna(row["hr_moy"]) else "—")
m5.metric("FC max", f"{row['hr_max']:.0f}" if pd.notna(row["hr_max"]) else "—")

_sport_details(sid, row["sport"])

# Carte GPS
geo = pts.dropna(subset=["lat", "lon"]) if not pts.empty else pd.DataFrame()
if not geo.empty:
    st.subheader("Trace GPS")
    center = [geo["lat"].mean(), geo["lon"].mean()]
    fmap = folium.Map(location=center, zoom_start=14, tiles="OpenStreetMap")
    folium.PolyLine(list(zip(geo["lat"], geo["lon"])), weight=4, color="#e2483d").add_to(fmap)
    folium.Marker([geo["lat"].iloc[0], geo["lon"].iloc[0]], tooltip="Depart",
                  icon=folium.Icon(color="green")).add_to(fmap)
    folium.Marker([geo["lat"].iloc[-1], geo["lon"].iloc[-1]], tooltip="Arrivee",
                  icon=folium.Icon(color="red")).add_to(fmap)
    fmap.fit_bounds([[geo["lat"].min(), geo["lon"].min()], [geo["lat"].max(), geo["lon"].max()]])
    st_folium(fmap, use_container_width=True, height=420, returned_objects=[])

# Courbes
CANAUX = ("hr", "vitesse", "altitude", "cadence", "puissance")
if not pts.empty and pts[[c for c in CANAUX if c in pts]].notna().any().any():
    st.subheader("Courbes")
    pts["t_min"] = pts["t_offset_s"] / 60.0
    show_pace = row["sport"] in ("course", "natation")
    # cle -> (libelle, serie, couleur, unite)
    courbes = {}
    if pts["hr"].notna().any():
        courbes["FC"] = ("FC", pts["hr"], "#e2483d", "bpm")
    if pts["vitesse"].notna().any():
        if show_pace:
            v = pts["vitesse"].where(pts["vitesse"] > 0.3)
            courbes["Allure"] = ("Allure", (1000.0 / 60.0) / v, "#2f6fed", "min/km")
        else:
            courbes["Vitesse"] = ("Vitesse", pts["vitesse"] * 3.6, "#2f6fed", "km/h")
    if pts["cadence"].notna().any():
        courbes["Cadence"] = ("Cadence", pts["cadence"], "#8e5bd0", "tr/min")
    if "puissance" in pts and pts["puissance"].notna().any():
        courbes["Puissance"] = ("Puissance", pts["puissance"], "#e8883a", "W")
    if pts["altitude"].notna().any():
        courbes["Altitude"] = ("Altitude", pts["altitude"], "#7a8b99", "m")

    defaut = [k for k in ("FC", "Allure", "Vitesse") if k in courbes]
    choix = st.multiselect("Courbes a afficher", list(courbes), default=defaut)
    if choix:
        fig = make_subplots(rows=len(choix), cols=1, shared_xaxes=True, vertical_spacing=0.04)
        for i, k in enumerate(choix, start=1):
            nom, serie, couleur, unite = courbes[k]
            kw = dict(fill="tozeroy") if k == "Altitude" else {}
            fig.add_trace(
                go.Scatter(x=pts["t_min"], y=serie, name=f"{nom} ({unite})", mode="lines",
                           line=dict(color=couleur, width=1.5), connectgaps=True, **kw),
                row=i, col=1,
            )
            fig.update_yaxes(title_text=unite, row=i, col=1)
            if k == "Allure":
                lo, hi = serie.quantile(0.02), serie.quantile(0.98)
                pad = (hi - lo) * 0.1
                fig.update_yaxes(range=[hi + pad, lo - pad], row=i, col=1)  # inverse
        fig.update_xaxes(title_text="Temps (min)", row=len(choix), col=1)
        fig.update_layout(height=max(280, 230 * len(choix)), hovermode="x unified",
                          margin=dict(t=50), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

# --- Edition RPE / notes ------------------------------------------------
st.divider()
with st.form("edit"):
    st.subheader("Ressenti & notes")
    rpe = st.slider("RPE (1-10)", 1, 10, int(row["ressenti_rpe"]) if pd.notna(row["ressenti_rpe"]) else 5)
    notes = st.text_area("Notes", value=row["notes"] or "")
    if st.form_submit_button("Enregistrer", type="primary"):
        with get_session() as db:
            obj = db.get(Session, int(sid))
            obj.ressenti_rpe = int(rpe)
            obj.notes = notes or None
        st.success("Mis a jour.")
        st.rerun()

contexte_page = (
    f"Page Seances. Seance selectionnee : #{sid} — {row['date']} — {row['sport']} — "
    f"{row['duree_min']:.0f} min, distance {row['distance_km']:.2f} km, "
    f"FC moy {row['hr_moy']}, RPE {row['ressenti_rpe']}."
)
widget_chat("seances", contexte_page)
