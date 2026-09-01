"""Calcul de charge interne (module tss.py) : cas connus par formule + cascade."""

from __future__ import annotations

from tss import Seuils, compute_tss, hr_tss, p_tss, r_tss, s_rpe, s_tss

_TH = Seuils(
    fc_max=200,
    fc_repos=60,
    fc_seuil=175,
    allure_seuil_course_s_km=300.0,   # 5'00 / km  -> 3.333 m/s
    allure_seuil_nat_s_100m=90.0,     # 1'30 / 100 m -> 1.111 m/s
    ftp_w=250.0,
)


def _hr_points(n_min: int, hr: int, step_s: int = 10) -> list[dict]:
    return [{"t_offset_s": i * step_s, "hr": hr} for i in range(n_min * 60 // step_s + 1)]


def test_hr_tss_one_hour_at_threshold_is_about_100():
    pts = _hr_points(60, hr=175)
    v = hr_tss(pts, _TH)
    assert v is not None and abs(v - 100) < 1.0


def test_hr_tss_easy_hour_is_well_below_100():
    pts = _hr_points(60, hr=120)  # ~endurance fondamentale
    v = hr_tss(pts, _TH)
    assert v is not None and 20 < v < 55


def test_r_tss_one_hour_at_threshold_pace_is_100():
    # vitesse moyenne = allure seuil -> IF = 1 -> 100 sur 1 h
    pts = [
        {"t_offset_s": 0, "distance_cum_m": 0.0},
        {"t_offset_s": 3600, "distance_cum_m": 3600 * (1000.0 / 300.0)},
    ]
    v = r_tss(3600, pts, _TH)
    assert v is not None and abs(v - 100) < 0.5


def test_s_tss_half_hour_at_threshold_is_50():
    v = s_tss(1800, allure_moy_s_100m=90.0, th=_TH)
    assert v is not None and abs(v - 50) < 0.5


def test_s_tss_faster_than_threshold_scales_quadratically():
    # nage 30 min a 1'20/100m (plus vite que le seuil 1'30) -> IF = 90/80 = 1.125
    v = s_tss(1800, allure_moy_s_100m=80.0, th=_TH)
    assert v is not None and abs(v - 0.5 * (90 / 80) ** 2 * 100) < 0.5


def test_p_tss_steady_at_ftp_one_hour_is_100():
    pts = [{"t_offset_s": i, "puissance": 250.0} for i in range(3601)]
    v = p_tss(3600, pts, _TH)
    assert v is not None and abs(v - 100) < 1.0


def test_s_rpe_scale():
    # RPE 7 pendant 60 min -> ~100
    v = s_rpe(3600, 7)
    assert v is not None and abs(v - 100) < 1.0


def test_cascade_swim_prefers_stss_when_pace_available():
    v, method = compute_tss(
        sport="natation", duree_s=1800, points=_hr_points(30, 150),
        th=_TH, allure_moy_s_100m=90.0,
    )
    assert method == "sTSS" and abs(v - 50) < 1.0


def test_cascade_swim_falls_back_to_hrtss_without_pace():
    v, method = compute_tss(
        sport="natation", duree_s=1800, points=_hr_points(30, 175), th=_TH,
    )
    assert method == "hrTSS" and v is not None


def test_cascade_bike_without_power_uses_hrtss():
    v, method = compute_tss(
        sport="velo", duree_s=3600, points=_hr_points(60, 175), th=_TH,
    )
    assert method == "hrTSS" and abs(v - 100) < 2.0


def test_cascade_bike_with_power_uses_ptss():
    pts = [{"t_offset_s": i, "puissance": 250.0, "hr": 175} for i in range(3601)]
    v, method = compute_tss(sport="velo", duree_s=3600, points=pts, th=_TH)
    assert method == "pTSS"


def test_cascade_renfo_no_hr_uses_srpe():
    v, method = compute_tss(sport="renfo", duree_s=3600, points=[], th=_TH, rpe=6)
    assert method == "sRPE" and v is not None


def test_cascade_returns_none_when_nothing_usable():
    v, method = compute_tss(sport="autre", duree_s=3600, points=[], th=_TH, rpe=None)
    assert v is None and method is None
