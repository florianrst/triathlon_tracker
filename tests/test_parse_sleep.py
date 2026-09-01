from __future__ import annotations

from datetime import date

from ingestion.parse_sleep import aggregate_sleep_ndjson

_LINES = """
{"timestamp":"2026-08-01T01:43:40.837+02:00","entryData":{"deepSleepDuration":3130.0,"duration":14000.0,"hrAvg":0.75,"hrMin":0.55,"quality":0.92}}
{"timestamp":"2026-08-01T04:30:00.000+02:00","entryData":{"deepSleepDuration":900.0,"duration":9000.0,"hrAvg":0.9,"hrMin":0.7,"quality":0.4}}
pas du json
{"timestamp":"2026-08-01T22:50:00.000+02:00","entryData":{"deepSleepDuration":3107.0,"duration":24923.0,"hrAvg":0.85,"hrMin":0.8,"quality":0.51}}
{"entryData":{"duration":1000.0}}
""".strip()


def test_aggregate_sleep_buckets_by_wake_day(tmp_path):
    f = tmp_path / "2026-08.ndjson"
    f.write_text(_LINES + "\n", encoding="utf-8")

    rows = {r["date"]: r for r in aggregate_sleep_ndjson(f)}
    # les 2 segments de nuit -> reveil le 1er ; le segment du soir (22:50) -> reveil le 2
    assert set(rows) == {date(2026, 8, 1), date(2026, 8, 2)}

    d1 = rows[date(2026, 8, 1)]
    assert d1["duree_totale_s"] == 14000 + 9000
    assert d1["sommeil_profond_s"] == 3130 + 900
    assert d1["n_segments"] == 2
    expected_q = (0.92 * 14000 + 0.4 * 9000) / (14000 + 9000)
    assert abs(d1["qualite"] - expected_q) < 1e-6
    assert d1["hr_nuit_min"] == 0.55
    assert abs(d1["hr_nuit_moy"] - (0.75 + 0.9) / 2) < 1e-6

    d2 = rows[date(2026, 8, 2)]
    assert d2["duree_totale_s"] == 24923
    assert d2["n_segments"] == 1


def test_aggregate_sleep_skips_malformed_and_missing_ts(tmp_path):
    f = tmp_path / "s.ndjson"
    f.write_text(
        '{"timestamp":"2026-08-03T02:00:00+02:00","entryData":{"duration":100.0}}\n'
        "garbage\n"
        '{"entryData":{"duration":999.0}}\n',
        encoding="utf-8",
    )
    rows = aggregate_sleep_ndjson(f)
    assert len(rows) == 1 and rows[0]["date"] == date(2026, 8, 3)


def test_evening_segment_attributed_to_next_day(tmp_path):
    f = tmp_path / "s.ndjson"
    f.write_text(
        '{"timestamp":"2026-08-10T23:30:00+02:00","entryData":{"duration":3600.0}}\n',
        encoding="utf-8",
    )
    rows = aggregate_sleep_ndjson(f)
    assert rows[0]["date"] == date(2026, 8, 11)
