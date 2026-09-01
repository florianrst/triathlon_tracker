from __future__ import annotations

import json
from pathlib import Path

from ingestion.parse_ndjson import aggregate_ndjson

LINES = [
    {"timestamp": "2026-06-02T20:10:00.000+02:00",
     "entryData": {"hr": 1.1666666, "stepCount": 11, "energyConsumption": 0.0}},
    {"timestamp": "2026-06-02T20:20:00.000+02:00",
     "entryData": {"hr": 0.9, "stepCount": 5, "energyConsumption": 2.5}},
    {"timestamp": "2026-06-03T07:00:00.000+02:00",
     "entryData": {"hr": 2.1, "stepCount": 40, "energyConsumption": 10.0}},
    "not-json",
    {"timestamp": "2026-06-03T07:10:00.000+02:00",
     "entryData": {"hr": 1.5, "stepCount": 20, "energyConsumption": 5.0}},
]


def test_aggregate_ndjson(tmp_path: Path):
    f = tmp_path / "passive.ndjson"
    f.write_text("\n".join(json.dumps(x) if isinstance(x, dict) else x for x in LINES))

    rows = aggregate_ndjson(f)
    assert [str(r["date"]) for r in rows] == ["2026-06-02", "2026-06-03"]

    d1 = rows[0]
    assert d1["steps_total"] == 16
    assert d1["energie_totale"] == 2.5
    assert d1["hr_ratio_min"] == 0.9
    assert abs(d1["hr_ratio_moy"] - (1.1666666 + 0.9) / 2) < 1e-6
    # champ hr non calibre -> jamais de bpm estime
    assert d1["hr_repos_estime"] is None
    assert d1["n_echantillons"] == 2

    d2 = rows[1]
    assert d2["steps_total"] == 60
    assert d2["hr_ratio_min"] == 1.5
