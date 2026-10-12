"""Config pytest : base SQLite temporaire, isolee du fichier de dev."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# doit etre defini AVANT le premier import de database.py
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
os.environ["TRIATHLON_DB_URL"] = f"sqlite:///{_TMP.name}"

import pytest  # noqa: E402

from core.database import engine, init_db  # noqa: E402
from core.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    yield


def pytest_sessionfinish(session, exitstatus):
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass
