"""Modeles SQLAlchemy pour le suivi triathlon.

Principes actes dans le brief :
- une table ``sessions`` commune + tables specifiques par sport (1-1) ;
- detail point-par-point conserve pour TOUTES les seances (``session_points``) ;
- zones et tests de seuil HISTORISES : jamais d'ecrasement, une ligne datee
  par recalcul.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Sport(str, enum.Enum):
    natation = "natation"
    velo = "velo"
    course = "course"
    renfo = "renfo"
    autre = "autre"


class SourceFormat(str, enum.Enum):
    fit = "fit"
    gpx = "gpx"
    manuel = "manuel"


class Discipline(str, enum.Enum):
    natation = "natation"
    velo = "velo"
    course = "course"


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    sport: Mapped[Sport] = mapped_column(SqlEnum(Sport), index=True)
    sous_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duree_s: Mapped[int] = mapped_column(Integer)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    d_plus_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_moy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_repos_jour: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ressenti_rpe: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # metriques derivees proprietaires reperees dans le FIT (cf. brief) :
    # temps de recuperation conseille et EPOC pic. Renseignees seulement
    # quand un FIT est disponible pour la seance.
    recovery_time_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_epoc: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_stress_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # charge calculee EN INTERNE (independante de la montre) : cf. module tss.py.
    # tss_methode = 'pTSS' | 'sTSS' | 'rTSS' | 'hrTSS' | 'sRPE'
    tss_calc: Mapped[float | None] = mapped_column(Float, nullable=True)
    tss_methode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    # cle "naturelle" de seance (nom de fichier sans extension) : permet de
    # dedoublonner une meme seance exportee a la fois en FIT et en GPX.
    source_key: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    source_format: Mapped[SourceFormat] = mapped_column(SqlEnum(SourceFormat))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    points: Mapped[list["SessionPoint"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="SessionPoint.t_offset_s"
    )
    swim: Mapped["SwimDetails | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    bike: Mapped["BikeDetails | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )
    run: Mapped["RunDetails | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class SessionPoint(Base):
    __tablename__ = "session_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    t_offset_s: Mapped[int] = mapped_column(Integer)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cadence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vitesse: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_cum_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    puissance: Mapped[float | None] = mapped_column(Float, nullable=True)  # W, si capteur (rare)

    session: Mapped[Session] = relationship(back_populates="points")


class SwimDetails(Base):
    __tablename__ = "swim_details"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    allure_moy_100m: Mapped[float | None] = mapped_column(Float, nullable=True)  # secondes / 100 m
    swolf: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nb_longueurs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stroke_type: Mapped[str | None] = mapped_column(String(30), nullable=True)

    session: Mapped[Session] = relationship(back_populates="swim")


class BikeDetails(Base):
    __tablename__ = "bike_details"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    puissance_moy_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    puissance_np_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    vitesse_moy_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    cadence_moy_rpm: Mapped[float | None] = mapped_column(Float, nullable=True)

    session: Mapped[Session] = relationship(back_populates="bike")


class RunDetails(Base):
    __tablename__ = "run_details"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    allure_moy_min_km: Mapped[float | None] = mapped_column(Float, nullable=True)  # minutes / km
    cadence_moy_spm: Mapped[float | None] = mapped_column(Float, nullable=True)
    oscillation_verticale: Mapped[float | None] = mapped_column(Float, nullable=True)

    session: Mapped[Session] = relationship(back_populates="run")


class ThresholdTest(Base):
    __tablename__ = "threshold_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    discipline: Mapped[Discipline] = mapped_column(SqlEnum(Discipline), index=True)
    type_test: Mapped[str] = mapped_column(String(60))
    valeur_brute: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrique_derivee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # seance support du test (« le 30 aout j'ai roule un test type ») : optionnel
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)

    zone_sets: Mapped[list["ZoneSet"]] = relationship(back_populates="source_test")


class AthleteThreshold(Base):
    """Seuils physiologiques HISTORISES (meme regle que ``ZoneSet`` : on date,
    on n'ecrase jamais). Alimentent le calcul de charge interne (``tss.py``).

    - ``fc_seuil`` : FC au seuil (SV2 / LTHR), bpm.
    - ``allure_seuil_s`` : allure au seuil, en s/100m (natation) ou s/km (course).
    - ``ftp_w`` : Functional Threshold Power, W (velo).
    """

    __tablename__ = "athlete_thresholds"

    id: Mapped[int] = mapped_column(primary_key=True)
    date_debut_validite: Mapped[date] = mapped_column(Date, index=True)
    discipline: Mapped[Discipline] = mapped_column(SqlEnum(Discipline), index=True)
    fc_seuil: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fc_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fc_repos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allure_seuil_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    ftp_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_test_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_tests.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ZoneSet(Base):
    __tablename__ = "zone_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    date_debut_validite: Mapped[date] = mapped_column(Date, index=True)
    discipline: Mapped[Discipline] = mapped_column(SqlEnum(Discipline), index=True)
    source_test_id: Mapped[int | None] = mapped_column(
        ForeignKey("threshold_tests.id"), nullable=True
    )
    zones_json: Mapped[dict] = mapped_column(JSON)

    source_test: Mapped[ThresholdTest | None] = relationship(back_populates="zone_sets")


class DailyPassive(Base):
    __tablename__ = "daily_passive"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    # champ `hr` du NDJSON = indice/ratio Suunto, PAS des bpm : on conserve le brut
    # agrege ; hr_repos_estime reste NULL tant que le ratio n'est pas calibre.
    hr_ratio_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_ratio_moy: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_repos_estime: Mapped[float | None] = mapped_column(Float, nullable=True)
    steps_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energie_totale: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_echantillons: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SleepDaily(Base):
    __tablename__ = "sleep_daily"

    # nuit rattachee au jour de reveil (segment le plus tardif < 12 h -> jour meme)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    duree_totale_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sommeil_profond_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualite: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    # hrAvg / hrMin de l'export = ratio Suunto NON calibre (~0.8-1.2), pas des bpm.
    hr_nuit_moy: Mapped[float | None] = mapped_column(Float, nullable=True)
    hr_nuit_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_segments: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RecoveryDaily(Base):
    __tablename__ = "recovery_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    balance_moy: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    stress_moy: Mapped[float | None] = mapped_column(Float, nullable=True)  # stressState 1..4
    pct_stress_eleve: Mapped[float | None] = mapped_column(Float, nullable=True)  # part stressState>=3
    n_echantillons: Mapped[int | None] = mapped_column(Integer, nullable=True)
