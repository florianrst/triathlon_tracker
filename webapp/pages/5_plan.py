"""Page Plan : calendrier de preparation 70.3 / XL sur ~1 an.

Plan genere (non persiste) a partir de la date de course cible et du volume
hebdo. Periodisation classique en blocs, avec semaines d'assimilation (recup)
toutes les 4 semaines et respect du 80/20 (rappel de la repartition cible).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.chat import widget_chat

st.set_page_config(page_title="Plan", page_icon="🗓️", layout="wide")

st.title("🗓️ Plan de preparation 70.3 / XL")

c1, c2, c3 = st.columns(3)
course = c1.date_input("Date de la course", value=date.today() + timedelta(weeks=40))
format_course = c2.selectbox("Format", ["70.3 (Half-Ironman)", "XL / Full"])
vol_max = c3.slider("Volume hebdo max (h)", 6, 18, 10)
vol_min = st.slider("Volume hebdo de depart (h)", 3, int(vol_max), min(6, vol_max))

start = date.today()
n_weeks = max(1, (course - start).days // 7)
if n_weeks < 8:
    st.warning("Moins de 8 semaines avant la course : plan tres compresse.")

# --- Definition des blocs (proportions de la duree totale) ------------------
blocs = [
    ("Preparation generale", 0.30, "Endurance de base, technique nat/velo, renfo. 100 % Z1-Z2."),
    ("Base / endurance", 0.28, "Montee du volume, sorties longues velo & course. 85/15."),
    ("Developpement / build", 0.24, "Intro seuil et allure course, briques velo-course. 80/20."),
    ("Specifique course", 0.12, "Allure cible 70.3/XL, nutrition, briques longues. 80/20."),
    ("Affutage / taper", 0.06, "Volume -40 a -60 %, on garde de l'intensite courte. 80/20."),
]

rows = []
acc = 0.0
wk_index = 0
for name, frac, focus in blocs:
    wcount = max(1, round(frac * n_weeks))
    for _ in range(wcount):
        if wk_index >= n_weeks:
            break
        wk_index += 1
        semaine_debut = start + timedelta(weeks=wk_index - 1)
        # rampe lineaire globale du volume, sauf taper (decru) et semaines de recup
        progress = wk_index / n_weeks
        base_vol = vol_min + (vol_max - vol_min) * min(1.0, progress / 0.85)
        is_taper = name.startswith("Affutage")
        is_recup = (wk_index % 4 == 0) and not is_taper
        if is_taper:
            vol = vol_max * (0.55 if wk_index < n_weeks else 0.4)
        elif is_recup:
            vol = base_vol * 0.6
        else:
            vol = base_vol
        rows.append({
            "Semaine": wk_index,
            "Debut": semaine_debut,
            "Bloc": name,
            "Type": "Assimilation" if is_recup else ("Affutage" if is_taper else "Charge"),
            "Volume (h)": round(vol, 1),
            "Z1-Z2 (h)": round(vol * 0.8, 1),
            "Haute int. (h)": round(vol * 0.2, 1),
            "Focus": focus,
        })

plan = pd.DataFrame(rows)
sem_course = plan["Semaine"].max() + 1
st.info(
    f"{n_weeks} semaines de prepa — du {start} au {course} "
    f"({format_course}). Volume {vol_min}→{vol_max} h/sem, 80/20 applique."
)

fig = px.bar(plan, x="Debut", y=["Z1-Z2 (h)", "Haute int. (h)"],
             color_discrete_map={"Z1-Z2 (h)": "#4c9a52", "Haute int. (h)": "#e2483d"},
             title="Volume hebdomadaire planifie (empile 80/20)")
fig.update_layout(barmode="stack", height=380, legend=dict(orientation="h"), yaxis_title="heures")
st.plotly_chart(fig, use_container_width=True)

st.dataframe(plan, use_container_width=True, hide_index=True)
st.download_button("Exporter le plan (CSV)", plan.to_csv(index=False).encode("utf-8"),
                   file_name="plan_prepa.csv", mime="text/csv")

with st.expander("Rappels methode"):
    st.markdown(
        "- **80/20 polarise** : 80 % du temps en endurance fondamentale (Z1-Z2, "
        "sous SV1), 20 % en haute intensite (Z4-Z5). Peu de Z3.\n"
        "- **Zones sur SV1/SV2**, ceinture pectorale.\n"
        "- **Semaine d'assimilation** toutes les 4 semaines (~-40 % de volume).\n"
        "- **Briques velo-course** a introduire en bloc Developpement, allongees en Specifique.\n"
        "- **Velo** : integrer travail de force/puissance quand le velo route est la."
    )

contexte_page = (
    f"Page Plan. Course cible : {format_course} le {course}. "
    f"{n_weeks} semaines de prepa, volume {vol_min}→{vol_max} h/sem, 80/20 applique."
)
widget_chat("plan", contexte_page)
