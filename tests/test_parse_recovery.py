from __future__ import annotations

from datetime import date

from ingestion.parse_recovery import aggregate_recovery_ndjson

_LINES = """
{"timestamp":"2026-08-01T15:30:00.000+02:00","entryData":{"balance":0.2,"stressState":4}}
{"timestamp":"2026-08-01T16:00:00.000+02:00","entryData":{"balance":0.4,"stressState":2}}
{"timestamp":"2026-08-01T16:30:00.000+02:00","entryData":{"balance":0.6,"stressState":3}}
bad line
{"timestamp":"2026-08-02T09:00:00.000+02:00","entryData":{"balance":0.8,"stressState":1}}
""".strip()


def test_aggregate_recovery_daily(tmp_path):
    f = tmp_path / "2026-08.ndjson"
    f.write_text(_LINES + "\n", encoding="utf-8")

    rows = {r["date"]: r for r in aggregate_recovery_ndjson(f)}
    assert set(rows) == {date(2026, 8, 1), date(2026, 8, 2)}

    d1 = rows[date(2026, 8, 1)]
    assert abs(d1["balance_moy"] - (0.2 + 0.4 + 0.6) / 3) < 1e-9
    assert d1["balance_min"] == 0.2
    assert abs(d1["stress_moy"] - (4 + 2 + 3) / 3) < 1e-9
    # 2 echantillons sur 3 a stressState >= 3
    assert abs(d1["pct_stress_eleve"] - 2 / 3) < 1e-9
    assert d1["n_echantillons"] == 3

    d2 = rows[date(2026, 8, 2)]
    assert d2["pct_stress_eleve"] == 0.0
    assert d2["n_echantillons"] == 1
