"""Calcul de charge d'entrainement (TSS) INDEPENDANT de la montre.

Cascade hybride par sport (approche TrainingPeaks / intervals.icu), du plus
precis au plus robuste :

    natation -> sTSS (allure /100m vs seuil)      [FC peu fiable dans l'eau]
    velo     -> pTSS (puissance) sinon hrTSS
    course   -> rTSS (allure vs allure seuil)  sinon hrTSS
    renfo / autre -> hrTSS sinon sRPE

Toutes les methodes sont calees sur la MEME echelle : 100 = 1 h a l'intensite
seuil. Fallback universel = hrTSS (TRIMP de Banister pondere par la reserve
cardiaque).

Fonctions pures, sans Streamlit ni acces DB. Entrees :
- ``duree_s`` : duree de la seance
- ``points`` : liste de dicts {t_offset_s, hr, vitesse, puissance, ...}
  (tels que stockes dans ``session_points``), ou ``None``
- ``th`` : objet ``Seuils`` (voir plus bas), jamais ``None`` -- l'appelant
  fournit au minimum le profil par defaut.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# --- Constantes TRIMP (Banister, ponderation exponentielle, homme) ----------
_TRIMP_K = 1.92
_TRIMP_B = 0.64


@dataclass(frozen=True)
class Seuils:
    """Seuils utiles au calcul, resolus par l'appelant pour la date de seance.

    ``fc_seuil`` doit toujours etre renseigne (au pire 0.9 * fc_max via le
    profil). Les autres sont optionnels et debloquent les methodes specifiques.
    """

    fc_max: float
    fc_repos: float
    fc_seuil: float
    allure_seuil_course_s_km: float | None = None   # s / km
    allure_seuil_nat_s_100m: float | None = None     # s / 100 m
    ftp_w: float | None = None


# --------------------------------------------------------------------------- #
# Briques                                                                      #
# --------------------------------------------------------------------------- #

def _trimp_pt(dt_min: float, hrr: float) -> float:
    hrr = min(1.0, max(0.0, hrr))
    return dt_min * hrr * _TRIMP_B * math.exp(_TRIMP_K * hrr)


def hr_tss(points: list[dict], th: Seuils) -> float | None:
    """TRIMP de Banister recale : 100 = 1 h a FC seuil.

    Integre point par point avec le dt reel entre echantillons (borne a 60 s
    pour absorber les trous de trace).
    """
    span = th.fc_max - th.fc_repos
    if span <= 0:
        return None
    hr_pts = [(p["t_offset_s"], p["hr"]) for p in points if p.get("hr")]
    if len(hr_pts) < 2:
        return None

    trimp = 0.0
    for (t0, hr0), (t1, _hr1) in zip(hr_pts, hr_pts[1:]):
        dt_min = min(max(t1 - t0, 0), 60) / 60.0
        hrr = (hr0 - th.fc_repos) / span
        trimp += _trimp_pt(dt_min, hrr)

    hrr_seuil = (th.fc_seuil - th.fc_repos) / span
    ref = _trimp_pt(60.0, hrr_seuil)
    if ref <= 0:
        return None
    return 100.0 * trimp / ref


def _pace_tss(duree_s: float, moy_vitesse_ms: float | None, seuil_vitesse_ms: float | None) -> float | None:
    """Forme commune rTSS / sTSS : IF = v_moy / v_seuil ; TSS = duree_h * IF^2 * 100."""
    if not moy_vitesse_ms or not seuil_vitesse_ms or seuil_vitesse_ms <= 0:
        return None
    intensity = moy_vitesse_ms / seuil_vitesse_ms
    return (duree_s / 3600.0) * intensity * intensity * 100.0


def _avg_speed_ms(points: list[dict], duree_s: float) -> float | None:
    """Vitesse moyenne : derniere distance cumulee / duree, sinon moyenne des vitesses points."""
    dists = [p["distance_cum_m"] for p in points if p.get("distance_cum_m") is not None]
    if dists and duree_s > 0:
        d = max(dists) - min(dists)
        if d > 0:
            return d / duree_s
    spds = [p["vitesse"] for p in points if p.get("vitesse")]
    return sum(spds) / len(spds) if spds else None


def r_tss(duree_s: float, points: list[dict], th: Seuils, *, avg_speed_ms: float | None = None) -> float | None:
    if th.allure_seuil_course_s_km is None:
        return None
    v = avg_speed_ms if avg_speed_ms is not None else _avg_speed_ms(points, duree_s)
    seuil_v = 1000.0 / th.allure_seuil_course_s_km
    return _pace_tss(duree_s, v, seuil_v)


def s_tss(duree_s: float, allure_moy_s_100m: float | None, th: Seuils) -> float | None:
    if th.allure_seuil_nat_s_100m is None or not allure_moy_s_100m or allure_moy_s_100m <= 0:
        return None
    v = 100.0 / allure_moy_s_100m
    seuil_v = 100.0 / th.allure_seuil_nat_s_100m
    return _pace_tss(duree_s, v, seuil_v)


def _rolling_mean(vals: list[float], win: int) -> list[float]:
    if win <= 1 or len(vals) <= win:
        return vals[:]
    out, acc = [], 0.0
    from collections import deque

    q: deque[float] = deque()
    for v in vals:
        q.append(v)
        acc += v
        if len(q) > win:
            acc -= q.popleft()
        out.append(acc / len(q))
    return out


def p_tss(duree_s: float, points: list[dict], th: Seuils) -> float | None:
    """Coggan : NP (moyenne mobile 30 s puis moyenne quadratique^4), IF = NP/FTP."""
    if not th.ftp_w or th.ftp_w <= 0:
        return None
    pw = [p["puissance"] for p in points if p.get("puissance") is not None]
    if len(pw) < 30:
        return None
    smoothed = _rolling_mean(pw, 30)
    np_ = (sum(x**4 for x in smoothed) / len(smoothed)) ** 0.25
    if np_ <= 0:
        return None
    intensity = np_ / th.ftp_w
    return (duree_s * np_ * intensity) / (th.ftp_w * 3600.0) * 100.0


def s_rpe(duree_s: float, rpe: int | None) -> float | None:
    """Foster : RPE(1-10) * duree_min, recale ~ 100 = 1 h a RPE 7 (diviseur 420)."""
    if not rpe:
        return None
    return (rpe * (duree_s / 60.0)) / 420.0 * 100.0


# --------------------------------------------------------------------------- #
# Routeur                                                                      #
# --------------------------------------------------------------------------- #

def compute_tss(
    *,
    sport: str,
    duree_s: float,
    points: list[dict] | None,
    th: Seuils,
    rpe: int | None = None,
    allure_moy_s_100m: float | None = None,
) -> tuple[float | None, str | None]:
    """Retourne ``(tss, methode)`` ou ``(None, None)`` si rien d'exploitable."""
    points = points or []

    if sport == "velo":
        v = p_tss(duree_s, points, th)
        if v is not None:
            return round(v, 1), "pTSS"
        v = hr_tss(points, th)
        if v is not None:
            return round(v, 1), "hrTSS"
        v = s_rpe(duree_s, rpe)
        return (round(v, 1), "sRPE") if v is not None else (None, None)

    if sport == "natation":
        v = s_tss(duree_s, allure_moy_s_100m, th)
        if v is not None:
            return round(v, 1), "sTSS"
        v = hr_tss(points, th)
        if v is not None:
            return round(v, 1), "hrTSS"
        v = s_rpe(duree_s, rpe)
        return (round(v, 1), "sRPE") if v is not None else (None, None)

    if sport == "course":
        v = r_tss(duree_s, points, th)
        if v is not None:
            return round(v, 1), "rTSS"
        v = hr_tss(points, th)
        if v is not None:
            return round(v, 1), "hrTSS"
        v = s_rpe(duree_s, rpe)
        return (round(v, 1), "sRPE") if v is not None else (None, None)

    # renfo / autre
    v = hr_tss(points, th)
    if v is not None:
        return round(v, 1), "hrTSS"
    v = s_rpe(duree_s, rpe)
    return (round(v, 1), "sRPE") if v is not None else (None, None)
