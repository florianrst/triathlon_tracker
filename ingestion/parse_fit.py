"""Parsing FIT (format natif Suunto/Garmin) -> dict normalise.

On extrait ce que ``fitparse`` expose facilement :
- messages ``record`` : position_lat/long, altitude, heart_rate, cadence,
  distance, speed, timestamp ;
- message ``session`` : duree, distance totale, HR moy/max, puissance, sport...

Pas de sur-investissement sur le parsing FIT en general, mais les quelques
metriques proprietaires reperees en cadrage (recovery_time, peak_epoc,
training_stress_score, feeling) sont recuperees quand presentes : elles
remontent au niveau racine du dict normalise (pas dans ``details``, qui reste
specifique au sport) et alimentent des colonnes dediees de ``sessions``.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from fitparse import FitFile

from .common import (
    SEMICIRCLE_TO_DEG,
    infer_points_kinematics,
    map_sous_type,
    map_sport,
    summarize_points,
)


def _val(msg, name):
    try:
        return msg.get_value(name)
    except Exception:  # pragma: no cover - defensif
        return None


def _first(fit: FitFile, msg_type: str):
    for m in fit.get_messages(msg_type):
        return m
    return None


def parse_fit(path: str | os.PathLike) -> dict:
    path = Path(path)
    fit = FitFile(str(path))
    fit.parse()

    records = list(fit.get_messages("record"))
    points: list[dict] = []
    t0 = None
    for r in records:
        ts = _val(r, "timestamp")
        if ts is None:
            continue
        if t0 is None:
            t0 = ts
        lat = _val(r, "position_lat")
        lon = _val(r, "position_long")
        hr = _val(r, "heart_rate")
        cad = _val(r, "cadence")
        spd = _val(r, "enhanced_speed")
        if spd is None:
            spd = _val(r, "speed")
        alt = _val(r, "enhanced_altitude")
        if alt is None:
            alt = _val(r, "altitude")
        pw = _val(r, "power")
        points.append(
            {
                "t_offset_s": int((ts - t0).total_seconds()),
                "lat": lat * SEMICIRCLE_TO_DEG if lat is not None else None,
                "lon": lon * SEMICIRCLE_TO_DEG if lon is not None else None,
                "altitude": float(alt) if alt is not None else None,
                "hr": int(hr) if hr is not None else None,
                "cadence": int(cad) if cad is not None else None,
                "vitesse": float(spd) if spd is not None else None,
                "distance_cum_m": float(_val(r, "distance")) if _val(r, "distance") is not None else None,
                "puissance": float(pw) if pw is not None else None,
            }
        )

    session_msg = _first(fit, "session")
    sport_raw = _val(session_msg, "sport") if session_msg else None
    sub_raw = _val(session_msg, "sub_sport") if session_msg else None

    if not points and session_msg is None:
        raise ValueError(f"FIT sans record ni session exploitables : {path.name}")

    if points:
        infer_points_kinematics(points)
    agg = summarize_points(points)

    # --- champs de synthese : session prioritaire, sinon calcule sur la trace
    def s(name):
        return _val(session_msg, name) if session_msg else None

    duree_s = s("total_timer_time") or s("total_elapsed_time")
    if duree_s is None and points:
        duree_s = points[-1]["t_offset_s"] - points[0]["t_offset_s"]
    duree_s = int(round(duree_s or 0))

    distance_m = s("total_distance") or agg["distance_m"]
    d_plus_m = s("total_ascent")
    if d_plus_m is None:
        d_plus_m = agg["d_plus_m"]
    hr_moy = s("avg_heart_rate") or agg["hr_moy"]
    hr_max = s("max_heart_rate") or agg["hr_max"]

    start_time = s("start_time") or t0
    seance_date: date = start_time.date() if start_time else date.today()

    sport = map_sport(sport_raw)
    if sport == "autre" and points:
        # trace GPS + vitesse plausible -> on n'invente pas, on laisse "autre"
        pass

    details = _build_details(sport, session_msg, s, duree_s, distance_m)

    # metriques proprietaires reperees dans le brief : recuperees si
    # presentes (uniquement dispo via le message `session` du FIT).
    recovery_time = s("recovery_time")
    peak_epoc = s("peak_epoc")
    tss = s("training_stress_score")
    feeling = s("feeling")

    return {
        "date": seance_date,
        "sport": sport,
        "sous_type": map_sous_type(sub_raw),
        "duree_s": duree_s,
        "distance_m": float(distance_m) if distance_m is not None else None,
        "d_plus_m": float(d_plus_m) if d_plus_m is not None else None,
        "hr_moy": int(hr_moy) if hr_moy is not None else None,
        "hr_max": int(hr_max) if hr_max is not None else None,
        "recovery_time_s": int(recovery_time) if recovery_time is not None else None,
        "peak_epoc": float(peak_epoc) if peak_epoc is not None else None,
        "training_stress_score": float(tss) if tss is not None else None,
        "feeling": _stringify(feeling),
        "source_file": path.name,
        "source_key": path.stem,
        "source_format": "fit",
        "points": points,
        "details": details,
    }


def _build_details(sport: str, session_msg, s, duree_s: int, distance_m) -> dict:
    if session_msg is None:
        return {}

    if sport == "natation":
        allure = None
        if distance_m and distance_m > 0 and duree_s:
            allure = duree_s / (distance_m / 100.0)  # s / 100 m
        return {
            "allure_moy_100m": allure,
            "swolf": s("avg_swolf") or s("swolf"),
            "nb_longueurs": s("num_lengths") or s("num_active_lengths"),
            "stroke_type": _stringify(s("swim_stroke")),
        }

    if sport == "velo":
        spd = s("enhanced_avg_speed") or s("avg_speed")
        return {
            "puissance_moy_w": s("avg_power"),
            "puissance_np_w": s("normalized_power"),
            "vitesse_moy_kmh": float(spd) * 3.6 if spd is not None else None,
            "cadence_moy_rpm": s("avg_cadence"),
        }

    if sport == "course":
        allure = None
        if distance_m and distance_m > 0 and duree_s:
            allure = (duree_s / 60.0) / (distance_m / 1000.0)  # min / km
        cad = s("avg_cadence")
        return {
            "allure_moy_min_km": allure,
            "cadence_moy_spm": float(cad) * 2 if cad is not None else None,  # pas complets
            "oscillation_verticale": s("avg_vertical_oscillation"),
        }

    return {}


def _stringify(v):
    if v is None:
        return None
    return str(v)
