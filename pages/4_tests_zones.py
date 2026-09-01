"""Page Tests & zones : tests de seuil + historique des zones (jamais ecrase)."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import select

from database import engine, get_session, init_db
from ingestion.seed import seed_calibration
from models import AthleteThreshold, Discipline, Session, ThresholdTest, ZoneSet

# course au sens large -> discipline "course"
_SPORT_FOR_DISCIPLINE = {"natation": ("natation",), "velo": ("velo",), "course": ("course",)}

st.set_page_config(page_title="Tests & zones", page_icon="🎯", layout="wide")
init_db()

st.title("🎯 Tests de seuil & zones")
st.caption(
    "Regle du projet : on DATE et on HISTORISE. Chaque nouveau test / recalcul "
    "cree une nouvelle ligne, jamais d'ecrasement — pour tracer la progression."
)

if st.button("Charger les donnees de calibrage initiales (prepa Olympique)"):
    res = seed_calibration()
    st.success(f"{res['tests']} test(s) et {res['zones']} set(s) de zones ajoutes.")

tests = pd.read_sql(select(ThresholdTest).order_by(ThresholdTest.date), engine)
zones = pd.read_sql(select(ZoneSet).order_by(ZoneSet.date_debut_validite), engine)
seuils = pd.read_sql(
    select(AthleteThreshold).order_by(AthleteThreshold.date_debut_validite), engine
)
for frame in (tests, zones, seuils):
    if not frame.empty and "discipline" in frame:
        frame["discipline"] = frame["discipline"].map(lambda s: getattr(s, "value", s))

sessions_df = pd.read_sql(
    select(Session.id, Session.date, Session.sport, Session.sous_type, Session.duree_s), engine
)
if not sessions_df.empty:
    sessions_df["sport"] = sessions_df["sport"].map(lambda s: getattr(s, "value", s))


def _sessions_near(discipline: str, around: date, delta_days: int = 3) -> pd.DataFrame:
    if sessions_df.empty:
        return sessions_df
    sports = _SPORT_FOR_DISCIPLINE.get(discipline, ())
    lo, hi = around - timedelta(days=delta_days), around + timedelta(days=delta_days)
    m = (
        sessions_df["sport"].isin(sports)
        & (sessions_df["date"] >= lo)
        & (sessions_df["date"] <= hi)
    )
    return sessions_df[m].sort_values("date")


def _session_label(sid: int) -> str:
    r = sessions_df[sessions_df["id"] == sid].iloc[0]
    st_txt = f"/{r['sous_type']}" if r["sous_type"] else ""
    return f"#{sid} — {r['date']} — {r['sport']}{st_txt} — {r['duree_s'] // 60} min"


# --- Nouveau test ---------------------------------------------------------
st.header("Nouveau test de seuil")
tc1, tc2 = st.columns(2)
t_disc = tc1.selectbox("Discipline", [e.value for e in Discipline], key="t_disc")
t_date = tc2.date_input("Date du test", value=date.today(), key="t_date")

near = _sessions_near(t_disc, t_date)
sess_choices = [None] + near["id"].tolist()
sess_id = st.selectbox(
    "Seance support (optionnel) — « le 30 aout j'ai roule un test type »",
    sess_choices,
    format_func=lambda i: "— aucune —" if i is None else _session_label(i),
    help="Rattache le test a une seance existante (± 3 jours de la date choisie).",
)
if sess_id is not None:
    srow = sessions_df[sessions_df["id"] == sess_id].iloc[0]
    t_date = srow["date"]  # la date du test = celle de la seance
    st.caption(f"Date alignee sur la seance : **{t_date}**.")

with st.form("test"):
    c3, c4, c5 = st.columns(3)
    type_test = c3.text_input("Type de test", placeholder="Cooper, FTP_30min, 2x100m…")
    valeur = c4.number_input("Valeur brute", value=0.0, help="ex: 2.82 (km au Cooper), 250 (W FTP)…")
    metrique = c5.text_input("Metrique derivee", placeholder="VMA 14.1 km/h, seuil 1'15/100m…")
    notes = st.text_area("Notes")
    if st.form_submit_button("Enregistrer le test", type="primary"):
        with get_session() as db:
            db.add(ThresholdTest(
                date=t_date, discipline=Discipline(t_disc), type_test=type_test or "test",
                valeur_brute=valeur or None, metrique_derivee=metrique or None,
                notes=notes or None, session_id=sess_id,
            ))
        st.success("Test enregistre.")
        st.rerun()

st.subheader("Historique des tests")
if tests.empty:
    st.info("Aucun test.")
else:
    show = tests[
        ["date", "discipline", "type_test", "valeur_brute", "metrique_derivee", "session_id", "notes"]
    ].copy()
    show["session_id"] = show["session_id"].map(
        lambda v: "" if pd.isna(v) else f"#{int(v)}"
    )
    st.dataframe(show, use_container_width=True, hide_index=True)
    num = tests.dropna(subset=["valeur_brute"])
    if not num.empty:
        fig = px.line(num, x="date", y="valeur_brute", color="discipline", markers=True,
                      title="Progression de la valeur brute par discipline")
        st.plotly_chart(fig, use_container_width=True)

# --- Profil / seuils physiologiques (historise) -------------------------
st.divider()
st.header("Profil / seuils (historise)")
st.caption(
    "Alimente le calcul de charge interne (page Charge). Sans ligne ici, le "
    "calcul retombe sur des valeurs par defaut (FC max 200, seuil ≈ 90 % FCmax). "
    "Relance ensuite `python -m scripts.recompute_tss --yes`."
)
with st.form("seuils"):
    s1, s2 = st.columns(2)
    s_date = s1.date_input("Debut de validite", value=date.today(), key="s_date")
    s_disc = s2.selectbox("Discipline", [e.value for e in Discipline], key="s_disc")
    s3, s4, s5 = st.columns(3)
    fc_seuil = s3.number_input("FC seuil (SV2 / LTHR, bpm)", min_value=0, value=0)
    fc_max = s4.number_input("FC max (bpm)", min_value=0, value=0)
    fc_repos = s5.number_input("FC repos (bpm)", min_value=0, value=0)
    s6, s7 = st.columns(2)
    allure_seuil = s6.text_input(
        "Allure seuil", placeholder="course: mm:ss/km — natation: mm:ss/100m",
        help="Saisie mm:ss (ex. 4:10). Vide = non renseigne.",
    )
    ftp = s7.number_input("FTP (W, velo)", min_value=0.0, value=0.0, step=5.0)
    s_notes = st.text_area("Notes", key="s_notes")
    src_test = st.selectbox(
        "Test source (optionnel)",
        [None] + (tests["id"].tolist() if not tests.empty else []),
        format_func=lambda i: "—" if i is None else f"#{i}",
    )
    if st.form_submit_button("Enregistrer les seuils", type="primary"):
        allure_s = None
        if allure_seuil.strip():
            try:
                mm, ss = allure_seuil.strip().split(":")
                allure_s = int(mm) * 60 + int(ss)
            except ValueError:
                st.error("Allure seuil : format attendu mm:ss (ex. 4:10).")
                st.stop()
        with get_session() as db:
            db.add(AthleteThreshold(
                date_debut_validite=s_date, discipline=Discipline(s_disc),
                fc_seuil=fc_seuil or None, fc_max=fc_max or None, fc_repos=fc_repos or None,
                allure_seuil_s=allure_s, ftp_w=ftp or None,
                source_test_id=src_test, notes=s_notes or None,
            ))
        st.success("Seuils enregistres. Pense a relancer le recalcul TSS.")
        st.rerun()

st.subheader("Historique des seuils")
if seuils.empty:
    st.info("Aucun seuil saisi.")
else:
    st.dataframe(
        seuils[["date_debut_validite", "discipline", "fc_seuil", "fc_max", "fc_repos",
                "allure_seuil_s", "ftp_w", "notes"]],
        use_container_width=True, hide_index=True,
    )
    prog = seuils.dropna(subset=["fc_seuil"])
    if not prog.empty:
        figs = px.line(prog, x="date_debut_validite", y="fc_seuil", color="discipline",
                       markers=True, title="Progression de la FC seuil")
        st.plotly_chart(figs, use_container_width=True)

# --- Nouveau set de zones -----------------------------------------------
st.divider()
st.header("Nouveau set de zones")
st.caption("Idealement ancre sur SV1 / SV2 plutot que sur un % de FCmax.")
with st.form("zones"):
    c1, c2, c3 = st.columns(3)
    zd = c1.date_input("Debut de validite", value=date.today(), key="zd")
    zdisc = c2.selectbox("Discipline", [e.value for e in Discipline], key="zdisc")
    src_options = [None] + (tests["id"].tolist() if not tests.empty else [])
    src = c3.selectbox("Test source (optionnel)", src_options,
                       format_func=lambda i: "—" if i is None else f"#{i}")
    default_json = json.dumps(
        {"Z1": "", "Z2": "", "Z3": "", "Z4": "", "Z5": ""}, indent=2, ensure_ascii=False
    )
    raw = st.text_area("Zones (JSON)", value=default_json, height=220)
    if st.form_submit_button("Enregistrer le set de zones", type="primary"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            st.error(f"JSON invalide : {exc}")
        else:
            with get_session() as db:
                db.add(ZoneSet(
                    date_debut_validite=zd, discipline=Discipline(zdisc),
                    source_test_id=src, zones_json=parsed,
                ))
            st.success("Set de zones enregistre.")
            st.rerun()

st.subheader("Historique des zones")
if zones.empty:
    st.info("Aucun set de zones.")
else:
    for disc in sorted(zones["discipline"].unique()):
        st.markdown(f"**{disc}**")
        sub = zones[zones["discipline"] == disc].sort_values("date_debut_validite", ascending=False)
        for _, z in sub.iterrows():
            src_txt = "" if pd.isna(z["source_test_id"]) else f"  (test #{int(z['source_test_id'])})"
            with st.expander(f"Valide a partir du {z['date_debut_validite']}{src_txt}"):
                st.json(z["zones_json"])
