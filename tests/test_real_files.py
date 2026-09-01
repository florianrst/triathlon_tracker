"""Tests optionnels sur les vrais fichiers de l'utilisateur.

Deposer des fichiers dans ``data/incoming/`` puis relancer pytest : ces tests
passent de "skipped" a "passed" et valident les parseurs sur des donnees
reelles Suunto.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.parse_fit import parse_fit
from ingestion.parse_gpx import parse_gpx
from ingestion.parse_ndjson import aggregate_ndjson

INCOMING = Path(__file__).resolve().parents[1] / "data" / "incoming"

# fichiers deposes a plat (essai rapide) OU arborescence Suunto complete
# (data/incoming/*/workouts, data/incoming/*/activity) -- on prend les deux.
FIT = sorted(INCOMING.glob("*.fit")) + sorted(INCOMING.glob("*/workouts/*.fit"))
GPX = sorted(INCOMING.glob("*.gpx")) + sorted(INCOMING.glob("*/workouts/*.gpx"))
NDJSON = (
    sorted(INCOMING.glob("*.ndjson"))
    + sorted(INCOMING.glob("*.jsonl"))
    + sorted(INCOMING.glob("*/activity/*.ndjson"))
)

# un gros export reel (~1000 seances) rendrait la suite trop lente : on se
# limite a un echantillon representatif pour ces tests de garde-fou.
_SAMPLE = 15
FIT = FIT[:_SAMPLE]
GPX = GPX[:_SAMPLE]
NDJSON = NDJSON[:_SAMPLE]


@pytest.mark.skipif(not FIT, reason="aucun .fit dans data/incoming/")
@pytest.mark.parametrize("path", FIT, ids=lambda p: p.name)
def test_real_fit(path):
    norm = parse_fit(path)
    assert norm["duree_s"] > 0
    assert norm["source_format"] == "fit"
    assert norm["sport"] in {"natation", "velo", "course", "renfo", "autre"}


@pytest.mark.skipif(not GPX, reason="aucun .gpx dans data/incoming/")
@pytest.mark.parametrize("path", GPX, ids=lambda p: p.name)
def test_real_gpx(path):
    norm = parse_gpx(path)
    assert norm["duree_s"] > 0
    assert len(norm["points"]) > 1


@pytest.mark.skipif(not NDJSON, reason="aucun .ndjson dans data/incoming/")
@pytest.mark.parametrize("path", NDJSON, ids=lambda p: p.name)
def test_real_ndjson(path):
    rows = aggregate_ndjson(path)
    assert rows
    assert all(r["hr_repos_estime"] is None for r in rows)
