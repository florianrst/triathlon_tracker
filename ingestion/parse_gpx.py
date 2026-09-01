"""Parsing GPX (export seance Suunto) -> dict normalise.

Source la plus fiable/simple pour le detail d'une seance : lat/lon/altitude/
timestamp point par point + extension ``gpxtpx:hr`` (FC reelle en bpm).
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from xml.etree.ElementTree import Element

import gpxpy

from .common import (
    infer_points_kinematics,
    map_sous_type,
    map_sport,
    summarize_points,
)

# tags d'extension par point : on cherche par nom local (sans namespace)
_EXT_KEYS = {
    "hr": "hr",
    "heartrate": "hr",
    "cad": "cadence",
    "cadence": "cadence",
    "atemp": "temp",
    "speed": "speed",
    "distance": "distance",
    "power": "power",
    "watts": "power",
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _walk_extensions(elements: list[Element], out: dict) -> None:
    for el in elements:
        key = _EXT_KEYS.get(_local(el.tag))
        if key and el.text and el.text.strip():
            try:
                out[key] = float(el.text.strip())
            except ValueError:
                pass
        if len(el):
            _walk_extensions(list(el), out)


def parse_gpx(path: str | os.PathLike) -> dict:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        gpx = gpxpy.parse(fh)

    points: list[dict] = []
    t0 = None
    sport_hint = None
    sub_hint = None

    for track in gpx.tracks:
        sport_hint = sport_hint or track.type
        for seg in track.segments:
            for pt in seg.points:
                if pt.time is None:
                    continue
                if t0 is None:
                    t0 = pt.time
                ext: dict = {}
                if pt.extensions:
                    _walk_extensions(list(pt.extensions), ext)
                points.append(
                    {
                        "t_offset_s": int((pt.time - t0).total_seconds()),
                        "lat": pt.latitude,
                        "lon": pt.longitude,
                        "altitude": pt.elevation,
                        "hr": int(ext["hr"]) if "hr" in ext else None,
                        "cadence": int(ext["cadence"]) if "cadence" in ext else None,
                        "vitesse": ext.get("speed"),
                        "distance_cum_m": ext.get("distance"),
                        "puissance": ext.get("power"),
                    }
                )

    if not points:
        raise ValueError(f"Aucun point exploitable dans le GPX : {path.name}")

    infer_points_kinematics(points)
    agg = summarize_points(points)

    duree_s = points[-1]["t_offset_s"] - points[0]["t_offset_s"]
    seance_date: date = (t0.date() if t0 else date.today())

    # heuristique sport : type de trace, sinon nom, sinon presence de deplacement
    name_blob = " ".join(
        filter(None, [sport_hint, gpx.name, *(t.name or "" for t in gpx.tracks)])
    ).lower()
    if "swim" in name_blob or "nat" in name_blob:
        sport = "natation"
    elif "bike" in name_blob or "cycl" in name_blob or "velo" in name_blob:
        sport = "velo"
    elif "run" in name_blob or "cours" in name_blob:
        sport = "course"
    else:
        sport = map_sport(sport_hint)

    return {
        "date": seance_date,
        "sport": sport,
        "sous_type": map_sous_type(sub_hint),
        "duree_s": int(duree_s),
        "distance_m": agg["distance_m"],
        "d_plus_m": agg["d_plus_m"],
        "hr_moy": agg["hr_moy"],
        "hr_max": agg["hr_max"],
        "source_file": path.name,
        "source_key": path.stem,
        "source_format": "gpx",
        "points": points,
        "details": {},
    }
