"""Agregation par periode + modele PMC (analysis.py)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from analysis import aggregate, performance_management
from ui.periode import Periode, _bornes, _decale


def _toy_sessions() -> pd.DataFrame:
    # 10 seances, 1 tous les 4 jours, a partir du 1er juin 2026
    rows = []
    d0 = date(2026, 6, 1)
    for i in range(10):
        rows.append(
            {
                "date": d0 + timedelta(days=4 * i),
                "duree_h": 1.0,
                "tss": 50.0,
                "sport": "course",
                "intensite": "basse",
            }
        )
    return pd.DataFrame(rows)


def _ramp_sessions() -> pd.DataFrame:
    # bloc de charge dense et croissant : ATL doit finir > CTL, TSB < 0
    rows = []
    d0 = date(2026, 6, 1)
    for i in range(28):
        rows.append(
            {
                "date": d0 + timedelta(days=i),
                "duree_h": 1.5,
                "tss": 60.0 + 2.0 * i,
                "sport": "course",
                "intensite": "basse",
            }
        )
    return pd.DataFrame(rows)


def test_aggregate_daily_weekly_monthly():
    df = _toy_sessions()

    par_jour = aggregate(df, "jour")
    assert len(par_jour) == 10
    assert par_jour["tss"].sum() == 500.0

    par_semaine = aggregate(df, "semaine")
    # 10 seances sur ~36 jours -> 6 semaines ISO touchees
    assert 5 <= len(par_semaine) <= 7
    assert par_semaine["n_seances"].sum() == 10

    par_mois = aggregate(df, "mois")
    assert list(par_mois["bucket"].dt.month) == [6, 7]
    assert par_mois["duree_h"].sum() == 10.0


def test_performance_management_shapes():
    df = _ramp_sessions()
    pmc = performance_management(df)
    # serie quotidienne continue du 1er jour au dernier
    assert (pmc["date"].diff().dropna() == pd.Timedelta(days=1)).all()
    assert {"tss_jour", "ctl", "atl", "tsb"} <= set(pmc.columns)
    # bloc de charge dense et croissant -> ATL (7 j) > CTL (42 j), TSB < 0
    assert pmc["atl"].iloc[-1] > pmc["ctl"].iloc[-1]
    assert pmc["tsb"].iloc[-1] < 0


def test_periode_bornes_and_navigation():
    lun = date(2026, 8, 24)  # un lundi
    assert _bornes("semaine", date(2026, 8, 26)) == (lun, date(2026, 8, 30))
    assert _bornes("mois", date(2026, 8, 15)) == (date(2026, 8, 1), date(2026, 8, 31))
    assert _bornes("annee", date(2026, 8, 15)) == (date(2026, 1, 1), date(2026, 12, 31))

    assert _decale("mois", date(2026, 1, 10), -1) == date(2025, 12, 1)
    assert _decale("semaine", lun, +1) == date(2026, 8, 31)
    assert _decale("annee", date(2026, 5, 1), +1) == date(2027, 1, 1)


def test_periode_libelle():
    p = Periode("mois", "semaine", date(2026, 8, 1), date(2026, 8, 31))
    assert "2026" in p.libelle()
