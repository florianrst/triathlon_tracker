"""Selecteur de periode reutilisable (pages Charge, Seances, Recuperation).

Trois echelles -- semaine / mois / annee -- avec, pour chacune, une
granularite de regroupement des graphes :

    semaine -> jour
    mois    -> jour | semaine
    annee   -> semaine | mois

Navigation < / > pour se deplacer d'une periode. L'etat est memorise dans
``st.session_state`` sous ``<key_prefix>_*`` pour que deux pages soient
independantes.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

import streamlit as st

_ECHELLES = ["semaine", "mois", "annee"]
_GRAINS = {
    "semaine": ["jour"],
    "mois": ["jour", "semaine"],
    "annee": ["semaine", "mois"],
}


@dataclass(frozen=True)
class Periode:
    echelle: str
    granularite: str
    debut: date
    fin: date  # inclus

    def libelle(self) -> str:
        if self.echelle == "semaine":
            return f"Semaine du {self.debut:%d/%m/%Y}"
        if self.echelle == "mois":
            return f"{calendar.month_name[self.debut.month].capitalize()} {self.debut.year}"
        return str(self.debut.year)


def _bornes(echelle: str, ancre: date) -> tuple[date, date]:
    if echelle == "semaine":
        debut = ancre - timedelta(days=ancre.weekday())
        return debut, debut + timedelta(days=6)
    if echelle == "mois":
        debut = ancre.replace(day=1)
        last = calendar.monthrange(debut.year, debut.month)[1]
        return debut, debut.replace(day=last)
    return date(ancre.year, 1, 1), date(ancre.year, 12, 31)


def _decale(echelle: str, ancre: date, sens: int) -> date:
    if echelle == "semaine":
        return ancre + timedelta(weeks=sens)
    if echelle == "mois":
        m = ancre.month - 1 + sens
        y = ancre.year + m // 12
        return date(y, m % 12 + 1, 1)
    return date(ancre.year + sens, 1, 1)


def selecteur_periode(key_prefix: str, *, defaut_echelle: str = "mois") -> Periode:
    k_ech, k_anc, k_gr = (f"{key_prefix}_{s}" for s in ("echelle", "ancre", "grain"))
    st.session_state.setdefault(k_ech, defaut_echelle)
    st.session_state.setdefault(k_anc, date.today())

    c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 3, 1])
    echelle = c1.selectbox("Echelle", _ECHELLES, key=k_ech)

    grains = _GRAINS[echelle]
    if st.session_state.get(k_gr) not in grains:
        st.session_state[k_gr] = grains[0]
    granularite = c2.selectbox("Grouper par", grains, key=k_gr)

    if c3.button("◀", key=f"{key_prefix}_prev"):
        st.session_state[k_anc] = _decale(echelle, st.session_state[k_anc], -1)
    if c5.button("▶", key=f"{key_prefix}_next"):
        st.session_state[k_anc] = _decale(echelle, st.session_state[k_anc], +1)

    debut, fin = _bornes(echelle, st.session_state[k_anc])
    periode = Periode(echelle, granularite, debut, fin)
    c4.markdown(f"### {periode.libelle()}")
    return periode
