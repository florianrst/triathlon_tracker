from __future__ import annotations

from datetime import date

from ingestion.common import merge_normalized, sport_from_filename


def test_sport_from_filename():
    assert sport_from_filename("2023-06-06_14.14.39-cycling.fit") == ("velo", "route")
    assert sport_from_filename("2023-06-07_17.35.26-swimming.gpx") == ("natation", "piscine")
    assert sport_from_filename("2023-06-06_15.08.30-running.fit") == ("course", "course")
    assert sport_from_filename("2024-01-01_08.00.00-mountain_biking.fit") == ("velo", "vtt")
    assert sport_from_filename("2024-01-01_08.00.00-gym.fit") == ("renfo", "renfo")
    assert sport_from_filename("2024-01-01_08.00.00-padel.gpx") == ("autre", "padel")


def test_sport_from_filename_sous_types_fins():
    # course au sens large : marche / rando / tapis / trail
    assert sport_from_filename("2025-09-25_09.41.03-walking.fit") == ("course", "marche")
    assert sport_from_filename("2023-09-22_14.54.01-hiking.gpx") == ("course", "rando")
    assert sport_from_filename("2025-01-01_07.00.00-treadmill.fit") == ("course", "tapis")
    assert sport_from_filename("2025-01-01_07.00.00-trail_running.fit") == ("course", "trail")
    # velo : route / vtt / home_trainer
    assert sport_from_filename("2026-07-09_20.06.26-indoor_cycling.fit") == ("velo", "home_trainer")
    assert sport_from_filename("2026-05-08_12.08.35-cycling.fit") == ("velo", "route")
    # eau libre
    assert sport_from_filename("2025-06-01_07.00.00-openwater_swimming.fit") == (
        "natation",
        "eau_libre",
    )
    # autres sports avec libelle lisible
    assert sport_from_filename("2025-01-01_10.00.00-downhill_skiing.gpx") == ("autre", "ski")


def test_sport_from_filename_no_token():
    assert sport_from_filename("2023-06.ndjson") == (None, None)
    assert sport_from_filename("no_dash_here.fit") == (None, None)


def _gpx_like(**over):
    base = dict(
        date=date(2024, 1, 1), sport="autre", sous_type=None, duree_s=1000,
        distance_m=3000.0, d_plus_m=10.0, hr_moy=130, hr_max=150,
        source_file="seance.gpx", source_key="seance", source_format="gpx",
        points=[{"t_offset_s": 0, "lat": 48.8, "lon": 2.3, "altitude": 30,
                 "hr": 130, "cadence": 80, "vitesse": 3.0, "distance_cum_m": 0.0}],
        details={},
    )
    base.update(over)
    return base


def _fit_like(**over):
    base = dict(
        date=date(2024, 1, 1), sport="course", sous_type=None, duree_s=1005,
        distance_m=3010.0, d_plus_m=12.0, hr_moy=132, hr_max=155,
        recovery_time_s=64800, peak_epoc=3.1, training_stress_score=40.0, feeling="3",
        source_file="seance.fit", source_key="seance", source_format="fit",
        points=[{"t_offset_s": 0, "lat": None, "lon": None, "altitude": None,
                 "hr": None, "cadence": None, "vitesse": None, "distance_cum_m": 0.0}],
        details={"allure_moy_min_km": 5.5},
    )
    base.update(over)
    return base


def test_merge_normalized_single_side_passthrough():
    gpx = _gpx_like()
    assert merge_normalized(gpx, None) is gpx
    fit = _fit_like()
    assert merge_normalized(None, fit) is fit


def test_merge_normalized_both_present():
    gpx, fit = _gpx_like(), _fit_like()
    merged = merge_normalized(gpx, fit)

    # trace : celle du GPX (position/hr reels)
    assert merged["points"] == gpx["points"]
    # synthese : FIT prioritaire quand present
    assert merged["duree_s"] == 1005
    assert merged["hr_moy"] == 132
    assert merged["hr_max"] == 155
    # metriques propres au FIT
    assert merged["recovery_time_s"] == 64800
    assert merged["peak_epoc"] == 3.1
    assert merged["training_stress_score"] == 40.0
    # details fusionnes
    assert merged["details"]["allure_moy_min_km"] == 5.5
    # sport : gpx etait "autre" -> bascule sur celui du FIT
    assert merged["sport"] == "course"
    # dedoublonnage sur le fichier GPX retenu comme source_file
    assert merged["source_file"] == "seance.gpx"
    assert merged["source_key"] == "seance"
    assert merged["source_format"] == "gpx"
    assert "seance.fit" in merged["notes"]


def test_merge_normalized_requires_one_side():
    import pytest

    with pytest.raises(ValueError):
        merge_normalized(None, None)
