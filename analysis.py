"""Calculs de synthese partages par les pages Streamlit.

Cadre de reference explicite de l'utilisateur : modele polarise 80/20
(80 % endurance fondamentale Z1-Z2, 20 % haute intensite). Les fonctions de
charge ci-dessous raisonnent en DUREE et ne doivent pas casser ce principe.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select

from database import engine, get_session
from models import Session, SessionPoint, ZoneSet

# --- Intensite d'une seance -------------------------------------------------

INTENSITES = ["basse", "moderee", "haute"]


def classify_intensity(rpe: int | None, frac_haute_hr: float | None) -> str:
    """Classe une seance. RPE prioritaire (saisie utilisateur), sinon HR.

    - RPE <= 4  -> basse
    - RPE 5-6   -> moderee
    - RPE >= 7  -> haute
    - sinon : > 15 % du temps passe > 85 % HRmax -> haute, sinon basse
    """
    if rpe is not None:
        if rpe <= 4:
            return "basse"
        if rpe <= 6:
            return "moderee"
        return "haute"
    if frac_haute_hr is not None and frac_haute_hr > 0.15:
        return "haute"
    return "basse"


def _hr_max_global() -> int | None:
    with get_session() as db:
        return db.scalar(select(Session.hr_max).order_by(Session.hr_max.desc()))


def sessions_dataframe() -> pd.DataFrame:
    """Toutes les seances + colonnes derivees (semaine ISO, intensite, charge)."""
    df = pd.read_sql(select(Session).order_by(Session.date), engine)
    if df.empty:
        return df

    hr_max_global = _hr_max_global() or 190

    # fraction du temps > 85 % HRmax global, par seance (une seule requete)
    pts = pd.read_sql(
        select(SessionPoint.session_id, SessionPoint.hr).where(SessionPoint.hr.isnot(None)),
        engine,
    )
    frac = {}
    if not pts.empty:
        seuil = 0.85 * hr_max_global
        g = pts.groupby("session_id")["hr"]
        frac = (g.apply(lambda s: (s >= seuil).mean())).to_dict()

    df["frac_haute_hr"] = df["id"].map(frac)
    df["intensite"] = [
        classify_intensity(r, f if pd.notna(f) else None)
        for r, f in zip(df["ressenti_rpe"], df["frac_haute_hr"])
    ]
    df["duree_h"] = df["duree_s"] / 3600.0
    # charge simple facon TRIMP : duree(min) * facteur d'intensite
    poids = {"basse": 1.0, "moderee": 2.0, "haute": 3.0}
    df["charge"] = df["duree_s"] / 60.0 * df["intensite"].map(poids)
    # TSS retenu : calcul maison (tss.py) en priorite, sinon celui de la montre,
    # sinon la charge TRIMP ramenee a une echelle ~comparable (100 = 1 h moyenne).
    tss = df["tss_calc"].copy()
    tss = tss.fillna(df["training_stress_score"])
    tss = tss.fillna(df["charge"] / 1.2)
    df["tss"] = tss
    df["semaine"] = pd.to_datetime(df["date"]).dt.to_period("W-MON").dt.start_time
    df["sport"] = df["sport"].map(lambda s: getattr(s, "value", s))
    return df


# --- Agregation par periode -----------------------------------------------

# libelle UI -> alias de periode pandas (Period : 'M', pas 'MS')
_GRAIN_TO_PERIOD = {"jour": "D", "semaine": "W-MON", "mois": "M"}


def aggregate(df: pd.DataFrame, granularite: str, valeurs=("duree_h", "tss")) -> pd.DataFrame:
    """Somme ``valeurs`` par bucket temporel (jour / semaine / mois).

    Renvoie un DataFrame indexe par le debut de bucket, colonnes = ``valeurs``
    (+ ``n_seances``).
    """
    if df.empty:
        return df
    period = _GRAIN_TO_PERIOD[granularite]
    key = pd.to_datetime(df["date"]).dt.to_period(period).dt.start_time
    cols = [c for c in valeurs if c in df.columns]
    out = df.groupby(key)[cols].sum()
    out["n_seances"] = df.groupby(key).size()
    out.index.name = "bucket"
    return out.reset_index()


def performance_management(df: pd.DataFrame) -> pd.DataFrame:
    """Modele PMC : CTL (42 j), ATL (7 j), TSB = CTL - ATL, a partir du TSS/jour.

    CTL/ATL en moyenne mobile exponentielle (constantes de temps classiques).
    """
    if df.empty:
        return df
    serie = (
        df.set_index(pd.to_datetime(df["date"]))["tss"].resample("D").sum().fillna(0.0)
    )
    pmc = pd.DataFrame({"tss_jour": serie})
    pmc["ctl"] = serie.ewm(span=42, adjust=False).mean()
    pmc["atl"] = serie.ewm(span=7, adjust=False).mean()
    pmc["tsb"] = pmc["ctl"] - pmc["atl"]
    pmc.index.name = "date"
    return pmc.reset_index()


def periodic_load(df: pd.DataFrame, granularite: str = "semaine") -> pd.DataFrame:
    """Agrege par bucket (jour/semaine/mois) : heures par sport + par intensite
    + %80/20. Colonne d'index nommee ``bucket``.
    """
    if df.empty:
        return df
    key = pd.to_datetime(df["date"]).dt.to_period(_GRAIN_TO_PERIOD[granularite]).dt.start_time
    tmp = df.assign(bucket=key)
    by_sport = tmp.pivot_table(
        index="bucket", columns="sport", values="duree_h", aggfunc="sum", fill_value=0
    )
    by_int = tmp.pivot_table(
        index="bucket", columns="intensite", values="duree_h", aggfunc="sum", fill_value=0
    )
    for col in INTENSITES:
        if col not in by_int:
            by_int[col] = 0.0
    out = by_sport.join(by_int, rsuffix="_int")
    out["total_h"] = tmp.groupby("bucket")["duree_h"].sum()
    out["tss"] = tmp.groupby("bucket")["tss"].sum()
    faible = by_int["basse"] + by_int["moderee"]
    out["pct_basse"] = (faible / out["total_h"] * 100).round(1)
    out["pct_haute"] = (by_int["haute"] / out["total_h"] * 100).round(1)
    return out.reset_index()


def weekly_load(df: pd.DataFrame) -> pd.DataFrame:
    """Compat : agregation hebdomadaire. Colonne d'index ``semaine``."""
    out = periodic_load(df, "semaine")
    return out.rename(columns={"bucket": "semaine"}) if not out.empty else out


def polarization_ratio(df: pd.DataFrame) -> tuple[float, float]:
    """(% temps basse+moderee, % temps haute) sur toute la periode."""
    if df.empty:
        return (0.0, 0.0)
    total = df["duree_h"].sum()
    if total == 0:
        return (0.0, 0.0)
    haute = df.loc[df["intensite"] == "haute", "duree_h"].sum()
    return round((total - haute) / total * 100, 1), round(haute / total * 100, 1)


# --- Zones historisees -------------------------------------------------------

def zone_history(discipline: str) -> pd.DataFrame:
    df = pd.read_sql(
        select(ZoneSet).where(ZoneSet.discipline == discipline).order_by(ZoneSet.date_debut_validite),
        engine,
    )
    return df
