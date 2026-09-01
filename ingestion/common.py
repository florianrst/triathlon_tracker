"""Helpers partages par les parseurs de seances.

Toutes les fonctions de parsing renvoient un dict "normalise" avec la meme
forme, consomme ensuite par :func:`ingestion.persist.persist_session`.

Forme du dict normalise ::

    {
        "date": date,
        "sport": "natation" | "velo" | "course" | "renfo" | "autre",
        "sous_type": str | None,
        "duree_s": int,
        "distance_m": float | None,
        "d_plus_m": float | None,
        "hr_moy": int | None,
        "hr_max": int | None,
        "source_file": str,          # nom de fichier (dedoublonnage)
        "source_format": "fit" | "gpx" | "manuel",
        "points": [
            {t_offset_s, lat, lon, altitude, hr, cadence, vitesse, distance_cum_m},
            ...
        ],
        "details": { ... },          # cle/valeur specifiques au sport, optionnel
    }
"""

from __future__ import annotations

import math
from typing import Any

# --- Correspondances sport -------------------------------------------------

# tokens (fichier Suunto OU champ `sport` du FIT) -> sport canonique
_SPORT_MAP = {
    # -- natation --
    "swimming": "natation",
    "swim": "natation",
    "open_water_swimming": "natation",
    "openwater_swimming": "natation",
    "lap_swimming": "natation",
    # -- velo --
    "cycling": "velo",
    "biking": "velo",
    "bike": "velo",
    "road_biking": "velo",
    "gravel_cycling": "velo",
    "cyclocross": "velo",
    "mountain_biking": "velo",
    "indoor_cycling": "velo",
    "virtual_cycling": "velo",
    "virtual_activity": "velo",
    "e_biking": "velo",
    # -- course (au sens large : tout ce qui se fait a pied) --
    "running": "course",
    "run": "course",
    "trail_running": "course",
    "treadmill": "course",
    "treadmill_running": "course",
    "indoor_running": "course",
    "walking": "course",
    "hiking": "course",
    # -- renfo --
    "training": "renfo",
    "strength_training": "renfo",
    "gym": "renfo",
    "fitness_equipment": "renfo",
    "core_training": "renfo",
    "yoga": "renfo",
    "pilates": "renfo",
    # -- tout le reste -> autre --
    "kayaking": "autre",
    "padel": "autre",
    "tennis": "autre",
    "climbing": "autre",
    "rock_climbing": "autre",
    "downhill_skiing": "autre",
    "cross_country_skiing": "autre",
    "snowboarding": "autre",
    "water_sports": "autre",
    "multisport": "autre",
    "triathlon": "autre",
    "generic": "autre",
}

# meme jeu de tokens -> sous_type explicite (granularite demandee par
# l'utilisateur : differencier route/vtt/home_trainer et course/marche/rando)
_SUBSPORT_MAP = {
    # natation
    "swimming": "piscine",
    "swim": "piscine",
    "lap_swimming": "piscine",
    "pool_swimming": "piscine",
    "open_water": "eau_libre",
    "openwater": "eau_libre",
    "openwater_swimming": "eau_libre",
    "open_water_swimming": "eau_libre",
    # velo
    "cycling": "route",
    "biking": "route",
    "bike": "route",
    "road": "route",
    "road_biking": "route",
    "cyclocross": "route",
    "gravel_cycling": "gravel",
    "gravel": "gravel",
    "mountain_biking": "vtt",
    "mountain": "vtt",
    "mtb": "vtt",
    "indoor_cycling": "home_trainer",
    "virtual_cycling": "home_trainer",
    "virtual_activity": "home_trainer",
    "spin": "home_trainer",
    "trainer": "home_trainer",
    # course
    "running": "course",
    "run": "course",
    "trail": "trail",
    "trail_running": "trail",
    "track": "piste",
    "treadmill": "tapis",
    "treadmill_running": "tapis",
    "indoor_running": "tapis",
    "walking": "marche",
    "hiking": "rando",
    # renfo
    "strength_training": "renfo",
    "gym": "renfo",
    "core_training": "renfo",
    "fitness_equipment": "renfo",
    "yoga": "yoga",
    "pilates": "pilates",
    # autre : garde un libelle lisible
    "downhill_skiing": "ski",
    "cross_country_skiing": "ski_fond",
    "snowboarding": "snowboard",
    "rock_climbing": "escalade",
    "climbing": "escalade",
    "kayaking": "kayak",
    "padel": "padel",
    "tennis": "tennis",
}


def sport_from_filename(name: str) -> tuple[str | None, str | None]:
    """(sport, sous_type) devine depuis un nom de fichier Suunto.

    Ex : ``2023-06-06_14.14.39-cycling.fit`` -> ("velo", "route").
    Renvoie ``(None, None)`` si aucun token reconnu (on laissera le parseur
    decider).
    """
    stem = name.rsplit("/", 1)[-1]
    for ext in (".fit", ".gpx", ".ndjson", ".jsonl"):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    if "-" not in stem:
        return None, None
    token = stem.rsplit("-", 1)[-1].strip().lower()
    if token in _SPORT_MAP:
        return _SPORT_MAP[token], _SUBSPORT_MAP.get(token)
    return None, None


def _clean_sous_type(value: str) -> str | None:
    """Filtre les sous-types parasites deja vus en base (ex. '85', '6', 'downhill').

    On n'accepte qu'un libelle alphabetique d'au moins 3 lettres (les '_' sont
    tolers : 'home_trainer', 'ski_fond'...).
    """
    stripped = value.replace("_", "")
    if len(stripped) < 3 or not stripped.isalpha():
        return None
    return value


def map_sport(raw: Any) -> str:
    if raw is None:
        return "autre"
    key = str(raw).strip().lower()
    return _SPORT_MAP.get(key, "autre")


def map_sous_type(raw: Any) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if key in ("", "generic", "all", "none"):
        return None
    if key in _SUBSPORT_MAP:
        return _SUBSPORT_MAP[key]
    return _clean_sous_type(key)


# --- Geometrie -----------------------------------------------------------------

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance grand-cercle en metres entre deux points WGS84."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


SEMICIRCLE_TO_DEG = 180.0 / (2**31)


# --- Agregats a partir des points -------------------------------------------

def summarize_points(points: list[dict]) -> dict:
    """Complete distance / d+ / hr moy-max a partir de la trace si absents."""
    hrs = [p["hr"] for p in points if p.get("hr")]
    dist = max((p["distance_cum_m"] for p in points if p.get("distance_cum_m")), default=None)

    d_plus = None
    alts = [(p["t_offset_s"], p["altitude"]) for p in points if p.get("altitude") is not None]
    if len(alts) >= 2:
        d_plus = 0.0
        prev = alts[0][1]
        for _, alt in alts[1:]:
            gain = alt - prev
            if gain > 0:
                d_plus += gain
            prev = alt

    return {
        "hr_moy": round(sum(hrs) / len(hrs)) if hrs else None,
        "hr_max": max(hrs) if hrs else None,
        "distance_m": dist,
        "d_plus_m": d_plus,
    }


def infer_points_kinematics(points: list[dict]) -> None:
    """Remplit distance_cum_m / vitesse in place si lat/lon dispo et champs vides."""
    last_ll: tuple[float, float] | None = None
    cum = 0.0
    have_dist = any(p.get("distance_cum_m") is not None for p in points)
    for i, p in enumerate(points):
        lat, lon = p.get("lat"), p.get("lon")
        if lat is not None and lon is not None:
            if last_ll is not None:
                cum += haversine_m(last_ll[0], last_ll[1], lat, lon)
            last_ll = (lat, lon)
            if not have_dist and p.get("distance_cum_m") is None:
                p["distance_cum_m"] = cum
        if p.get("vitesse") is None and i > 0:
            prev = points[i - 1]
            dt = p["t_offset_s"] - prev["t_offset_s"]
            d0 = prev.get("distance_cum_m")
            d1 = p.get("distance_cum_m")
            if dt and dt > 0 and d0 is not None and d1 is not None:
                p["vitesse"] = max(0.0, (d1 - d0) / dt)


# --- Fusion FIT + GPX d'une meme seance --------------------------------------

# constat verifie sur les fichiers reels de l'utilisateur (pas une hypothese) :
# selon le sport, ni le FIT ni le GPX n'est strictement le plus complet.
# `record` FIT : distance+timestamp (+heart_rate en course), jamais de
# lat/lon/altitude/cadence sur ce modele de montre. GPX : lat/lon reels (0,0
# factices en piscine) + hr + cad par point. Le message `session` du FIT en
# revanche est la seule source des metriques de synthese (avg/max HR, SWOLF,
# recovery_time, peak_epoc, training_stress_score...).
# -> GPX fournit la trace point-par-point, FIT fournit la synthese.
_SUMMARY_KEYS = ("duree_s", "distance_m", "d_plus_m", "hr_moy", "hr_max")
_FIT_ONLY_KEYS = ("recovery_time_s", "peak_epoc", "training_stress_score", "feeling")


def merge_normalized(gpx_norm: dict | None, fit_norm: dict | None) -> dict:
    """Fusionne les dicts normalises GPX + FIT d'une meme seance (meme stem).

    Un seul des deux fourni -> renvoye tel quel (pas de fusion). Les deux
    fournis -> trace du GPX, synthese/metriques proprietaires du FIT quand
    disponibles, details sport-specifiques fusionnes (FIT prioritaire).
    """
    if gpx_norm and not fit_norm:
        return gpx_norm
    if fit_norm and not gpx_norm:
        return fit_norm
    if not gpx_norm and not fit_norm:
        raise ValueError("merge_normalized: au moins un des deux dicts est requis")

    merged = dict(gpx_norm)
    merged["points"] = gpx_norm["points"] or fit_norm.get("points", [])

    for key in _SUMMARY_KEYS:
        if fit_norm.get(key) is not None:
            merged[key] = fit_norm[key]

    for key in _FIT_ONLY_KEYS:
        merged[key] = fit_norm.get(key)

    merged["details"] = {
        **gpx_norm.get("details", {}),
        **{k: v for k, v in fit_norm.get("details", {}).items() if v is not None},
    }

    if gpx_norm.get("sport") in (None, "autre") and fit_norm.get("sport"):
        merged["sport"] = fit_norm["sport"]
    if not merged.get("sous_type") and fit_norm.get("sous_type"):
        merged["sous_type"] = fit_norm["sous_type"]

    merged["source_file"] = gpx_norm["source_file"]
    merged["source_key"] = gpx_norm.get("source_key") or fit_norm.get("source_key")
    merged["source_format"] = "gpx"  # format de la trace retenue

    fit_name = fit_norm.get("source_file")
    if fit_name:
        note = f"FIT: {fit_name}"
        merged["notes"] = f"{merged['notes']}\n{note}" if merged.get("notes") else note

    return merged
