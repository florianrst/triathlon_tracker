"""Resolution des seuils (``tss.Seuils``) valides a une date donnee.

Prend la ligne ``athlete_thresholds`` la plus recente dont
``date_debut_validite <= date_seance``, par discipline. Ce qui manque est
comble par le profil (``athlete.load_profil``) : au pire, ``fc_seuil`` retombe
sur ~90 % de la FC max.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import select

from athlete.profil import load_profil
from core.database import engine
from core.models import AthleteThreshold, Discipline
from core.tss import Seuils

# course au sens large (marche, rando, trail, tapis) -> discipline "course"
_SPORT_TO_DISCIPLINE = {"natation": "natation", "velo": "velo", "course": "course"}


def _thresholds_frame() -> pd.DataFrame:
    df = pd.read_sql(
        select(AthleteThreshold).order_by(AthleteThreshold.date_debut_validite), engine
    )
    if not df.empty:
        df["discipline"] = df["discipline"].map(lambda s: getattr(s, "value", s))
        df["date_debut_validite"] = pd.to_datetime(df["date_debut_validite"]).dt.date
    return df


class ThresholdResolver:
    """Charge la table une fois, resout par (sport, date) a la volee."""

    def __init__(self) -> None:
        self._df = _thresholds_frame()
        self._profil = load_profil()

    def _row_for(self, discipline: str, on: date) -> dict | None:
        if self._df.empty:
            return None
        sub = self._df[
            (self._df["discipline"] == discipline)
            & (self._df["date_debut_validite"] <= on)
        ]
        if sub.empty:
            return None
        return sub.iloc[-1].to_dict()

    def seuils_for(self, sport: str, on: date) -> Seuils:
        p = self._profil
        fc_max, fc_repos, fc_seuil = float(p.fc_max), float(p.fc_repos), p.fc_seuil_estime
        allure_course = allure_nat = ftp = None

        discipline = _SPORT_TO_DISCIPLINE.get(sport)
        row = self._row_for(discipline, on) if discipline else None
        if row:
            if row.get("fc_max"):
                fc_max = float(row["fc_max"])
            if row.get("fc_repos") is not None:
                fc_repos = float(row["fc_repos"])
            if row.get("fc_seuil"):
                fc_seuil = float(row["fc_seuil"])
            elif row.get("fc_max"):
                fc_seuil = 0.90 * fc_max
            if discipline == "course" and row.get("allure_seuil_s"):
                allure_course = float(row["allure_seuil_s"])
            if discipline == "natation" and row.get("allure_seuil_s"):
                allure_nat = float(row["allure_seuil_s"])
            if discipline == "velo" and row.get("ftp_w"):
                ftp = float(row["ftp_w"])

        return Seuils(
            fc_max=fc_max,
            fc_repos=fc_repos,
            fc_seuil=fc_seuil,
            allure_seuil_course_s_km=allure_course,
            allure_seuil_nat_s_100m=allure_nat,
            ftp_w=ftp,
        )
