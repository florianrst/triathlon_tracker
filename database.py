"""Configuration de la base de donnees (SQLAlchemy).

Portable SQLite -> Postgres : l'URL est lue depuis la variable
d'environnement ``TRIATHLON_DB_URL`` et retombe sur un fichier SQLite
local (``data/triathlon.db``) sinon.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INCOMING_DIR = DATA_DIR / "incoming"
DATA_DIR.mkdir(exist_ok=True)
INCOMING_DIR.mkdir(exist_ok=True)

DEFAULT_SQLITE_URL = f"sqlite:///{DATA_DIR / 'triathlon.db'}"
DATABASE_URL = os.environ.get("TRIATHLON_DB_URL", DEFAULT_SQLITE_URL)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=_connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


# Colonnes ajoutees APRES coup a des tables existantes. `create_all` ne les
# ajoute pas (il ne cree que les tables absentes) et le projet n'a pas
# d'Alembic -> petite migration idempotente au demarrage. Type SQLite simple.
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "sessions": {"tss_calc": "FLOAT", "tss_methode": "VARCHAR(10)"},
    "session_points": {"puissance": "FLOAT"},
    "threshold_tests": {"session_id": "INTEGER"},
}


def _apply_light_migrations() -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue  # create_all vient de la creer avec les colonnes a jour
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))


def init_db() -> None:
    """Cree les tables manquantes + ajoute les colonnes recentes. Idempotent."""
    from models import Base  # import tardif pour eviter les cycles

    Base.metadata.create_all(engine)
    _apply_light_migrations()


@contextmanager
def get_session() -> Iterator[Session]:
    """Context manager de session avec commit / rollback automatiques."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
