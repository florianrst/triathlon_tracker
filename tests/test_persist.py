from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from database import get_session
from ingestion import persist as persist_module
from ingestion.persist import (
    _process_session_group,
    persist_daily_passive,
    persist_recovery_daily,
    persist_session,
    persist_sleep_daily,
)
from ingestion.seed import seed_calibration
from models import DailyPassive, RecoveryDaily, RunDetails, Session, SessionPoint, SleepDaily


def _norm():
    return {
        "date": date(2026, 6, 2),
        "sport": "course",
        "sous_type": "route",
        "duree_s": 3000,
        "distance_m": 10000.0,
        "d_plus_m": 50.0,
        "hr_moy": 150,
        "hr_max": 175,
        "ressenti_rpe": 6,
        "notes": None,
        "source_file": "run-001.gpx",
        "source_key": "run-001",
        "source_format": "gpx",
        "points": [
            {"t_offset_s": 0, "lat": 48.8, "lon": 2.3, "altitude": 30, "hr": 140,
             "cadence": 85, "vitesse": 3.0, "distance_cum_m": 0.0},
            {"t_offset_s": 10, "lat": 48.8, "lon": 2.3, "altitude": 32, "hr": 150,
             "cadence": 86, "vitesse": 3.2, "distance_cum_m": 31.0},
        ],
        "details": {"allure_moy_min_km": 5.0, "cadence_moy_spm": 172.0},
    }


def test_persist_and_dedup():
    r1 = persist_session(_norm())
    assert r1.status == "imported"

    r2 = persist_session(_norm())
    assert r2.status == "duplicate"

    with get_session() as db:
        assert db.scalar(select(func.count()).select_from(Session)) == 1
        assert db.scalar(select(func.count()).select_from(SessionPoint)) == 2
        det = db.scalar(select(RunDetails))
        assert det is not None and det.allure_moy_min_km == 5.0


def test_reimport_same_key_is_duplicate():
    """Un re-scan qui reverrait la meme seance sous un autre nom de fichier
    (ex. re-fusion FIT+GPX) ne doit pas creer de doublon."""
    r1 = persist_session(_norm())
    assert r1.status == "imported"

    other_file = dict(_norm())
    other_file["source_file"] = "run-001-bis.gpx"  # meme source_key
    r2 = persist_session(other_file)
    assert r2.status == "duplicate"

    with get_session() as db:
        assert db.scalar(select(func.count()).select_from(Session)) == 1


def test_persist_session_stores_fit_only_metrics():
    norm = _norm()
    norm.update(
        source_file="run-002.gpx", source_key="run-002",
        recovery_time_s=64800, peak_epoc=3.2, training_stress_score=45.6,
    )
    persist_session(norm)
    with get_session() as db:
        s = db.scalar(select(Session).where(Session.source_key == "run-002"))
        assert s.recovery_time_s == 64800
        assert s.peak_epoc == 3.2
        assert s.training_stress_score == 45.6


def test_session_group_survives_broken_gpx(monkeypatch, tmp_path):
    """Un GPX sans trace exploitable (frequent pour gym/renfo) ne doit pas
    faire perdre le FIT correspondant."""
    gpx_path = tmp_path / "2023-07-27_07.56.05-gym.gpx"
    fit_path = tmp_path / "2023-07-27_07.56.05-gym.fit"
    gpx_path.touch()
    fit_path.touch()

    fit_norm = {
        "date": date(2023, 7, 27), "sport": "renfo", "sous_type": None,
        "duree_s": 1034, "distance_m": None, "d_plus_m": None,
        "hr_moy": 110, "hr_max": 140,
        "recovery_time_s": 3600, "peak_epoc": 1.1, "training_stress_score": 20.0,
        "feeling": "3",
        "source_file": fit_path.name, "source_key": fit_path.stem, "source_format": "fit",
        "points": [], "details": {},
    }

    def _fake_parse_gpx(path):
        raise ValueError(f"Aucun point exploitable dans le GPX : {path.name}")

    monkeypatch.setattr(persist_module, "parse_gpx", _fake_parse_gpx)
    monkeypatch.setattr(persist_module, "parse_fit", lambda path: fit_norm)

    result = _process_session_group({".gpx": gpx_path, ".fit": fit_path})
    assert result.status == "imported"
    assert "partiel" in result.detail

    with get_session() as db:
        s = db.scalar(select(Session).where(Session.source_key == fit_path.stem))
        assert s is not None
        assert s.source_format.value == "fit"
        assert s.duree_s == 1034
        assert s.sport.value == "renfo"


def test_persist_daily_passive_upsert():
    rows = [{"date": date(2026, 6, 2), "hr_ratio_min": 0.9, "hr_ratio_moy": 1.0,
             "hr_repos_estime": None, "steps_total": 100, "energie_totale": 5.0,
             "n_echantillons": 3}]
    assert persist_daily_passive(rows) == 1
    rows[0]["steps_total"] = 250
    assert persist_daily_passive(rows) == 1
    with get_session() as db:
        obj = db.get(DailyPassive, date(2026, 6, 2))
        assert obj.steps_total == 250


def test_persist_sleep_daily_upsert_merge_safe():
    rows = [{"date": date(2026, 8, 1), "duree_totale_s": 25000, "sommeil_profond_s": 3000,
             "qualite": 0.8, "hr_nuit_moy": 0.75, "hr_nuit_min": 0.6, "n_segments": 1}]
    assert persist_sleep_daily(rows) == 1
    # nouvelle agregation avec MOINS de segments : ne doit pas ecraser
    stale = [dict(rows[0], duree_totale_s=1, n_segments=0)]
    assert persist_sleep_daily(stale) == 0
    # agregation plus complete : ecrase
    fuller = [dict(rows[0], duree_totale_s=30000, n_segments=2)]
    assert persist_sleep_daily(fuller) == 1
    with get_session() as db:
        obj = db.get(SleepDaily, date(2026, 8, 1))
        assert obj.duree_totale_s == 30000 and obj.n_segments == 2


def test_persist_recovery_daily_upsert():
    rows = [{"date": date(2026, 8, 1), "balance_moy": 0.4, "balance_min": 0.2,
             "stress_moy": 2.5, "pct_stress_eleve": 0.3, "n_echantillons": 40}]
    assert persist_recovery_daily(rows) == 1
    rows[0]["balance_moy"] = 0.55
    assert persist_recovery_daily(rows) == 1
    with get_session() as db:
        assert db.get(RecoveryDaily, date(2026, 8, 1)).balance_moy == 0.55


def test_process_passive_routes_by_parent_dir(tmp_path):
    sleep_dir = tmp_path / "suivi" / "sleep"
    rec_dir = tmp_path / "suivi" / "recovery"
    sleep_dir.mkdir(parents=True)
    rec_dir.mkdir(parents=True)
    (sleep_dir / "2026-08.ndjson").write_text(
        '{"timestamp":"2026-08-01T02:00:00+02:00","entryData":{"duration":25000.0,"deepSleepDuration":3000.0,"quality":0.8,"hrAvg":0.75,"hrMin":0.6}}\n',
        encoding="utf-8",
    )
    (rec_dir / "2026-08.ndjson").write_text(
        '{"timestamp":"2026-08-01T15:00:00+02:00","entryData":{"balance":0.3,"stressState":4}}\n',
        encoding="utf-8",
    )
    r1 = persist_module._process_passive(sleep_dir / "2026-08.ndjson")
    r2 = persist_module._process_passive(rec_dir / "2026-08.ndjson")
    assert r1.status == "passive" and "sommeil" in r1.detail
    assert r2.status == "passive" and "recup" in r2.detail
    with get_session() as db:
        assert db.get(SleepDaily, date(2026, 8, 1)) is not None
        assert db.get(RecoveryDaily, date(2026, 8, 1)) is not None


def test_seed_calibration_idempotent():
    a = seed_calibration()
    assert a["tests"] > 0 and a["zones"] > 0
    b = seed_calibration()
    assert b == {"tests": 0, "zones": 0}
