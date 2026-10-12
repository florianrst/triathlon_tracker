"""Insertion en base des dicts normalises + dispatch par type de fichier.

Point d'entree principal : :func:`ingest_paths`, qui regroupe les fichiers
FIT/GPX d'une meme seance (meme nom sans extension) pour les fusionner via
:func:`ingestion.common.merge_normalized` avant insertion -- evite de choisir
arbitrairement un format « gagnant ».
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Callable

from sqlalchemy import insert, select

from core.database import get_session
from core.models import (
    BikeDetails,
    DailyPassive,
    RecoveryDaily,
    RunDetails,
    Session,
    SessionPoint,
    SleepDaily,
    SourceFormat,
    Sport,
    SwimDetails,
)

from .common import merge_normalized, sport_from_filename
from .parse_fit import parse_fit
from .parse_gpx import parse_gpx
from .parse_ndjson import aggregate_ndjson
from .parse_recovery import aggregate_recovery_ndjson
from .parse_sleep import aggregate_sleep_ndjson

SESSION_EXTS = {".fit": parse_fit, ".gpx": parse_gpx}
PASSIVE_EXTS = {".ndjson", ".jsonl"}
# le type de donnee passive est determine par le dossier parent de l'export Suunto
_SLEEP_DIR = "sleep"
_RECOVERY_DIR = "recovery"

ProgressCB = Callable[[int, int, "IngestResult"], None]


class IngestResult:
    def __init__(self, path: str, status: str, detail: str = ""):
        self.path = path
        self.status = status  # imported | duplicate | passive | skipped | error
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IngestResult {self.status} {Path(self.path).name} {self.detail}>"


def _apply_details(db, session_id: int, sport: str, details: dict) -> None:
    if not details:
        return
    clean = {k: v for k, v in details.items() if v is not None}
    if not clean:
        return
    if sport == Sport.natation.value:
        db.add(SwimDetails(session_id=session_id, **clean))
    elif sport == Sport.velo.value:
        db.add(BikeDetails(session_id=session_id, **clean))
    elif sport == Sport.course.value:
        db.add(RunDetails(session_id=session_id, **clean))


def persist_session(
    norm: dict, *, sport_override: str | None = None, sous_type_override: str | None = None
) -> IngestResult:
    """Insere une seance normalisee (deja fusionnee FIT+GPX si besoin).

    Dedoublonnage sur ``source_file`` (meme fichier) ET ``source_key``
    (meme seance re-scannee) : protege les ré-scans du dossier surveille.
    """
    source_file = norm["source_file"]
    source_key = norm.get("source_key")
    sport = sport_override or norm["sport"]
    sous_type = sous_type_override or norm.get("sous_type")

    with get_session() as db:
        if db.scalar(select(Session.id).where(Session.source_file == source_file)):
            return IngestResult(source_file, "duplicate", "fichier deja importe")
        if source_key and db.scalar(select(Session.id).where(Session.source_key == source_key)):
            return IngestResult(source_file, "duplicate", "seance deja importee")

        session = Session(
            date=norm["date"],
            sport=Sport(sport),
            sous_type=sous_type,
            duree_s=norm["duree_s"],
            distance_m=norm.get("distance_m"),
            d_plus_m=norm.get("d_plus_m"),
            hr_moy=norm.get("hr_moy"),
            hr_max=norm.get("hr_max"),
            ressenti_rpe=norm.get("ressenti_rpe"),
            notes=norm.get("notes"),
            recovery_time_s=norm.get("recovery_time_s"),
            peak_epoc=norm.get("peak_epoc"),
            training_stress_score=norm.get("training_stress_score"),
            source_file=source_file,
            source_key=source_key,
            source_format=SourceFormat(norm["source_format"]),
        )
        db.add(session)
        db.flush()

        points = norm.get("points", [])
        if points:
            db.execute(
                insert(SessionPoint),
                [{"session_id": session.id, **p} for p in points],
            )

        details = norm.get("details", {})
        _apply_details(db, session.id, sport, details)

        tss_val, tss_method = _compute_session_tss(norm, sport, points, details)
        session.tss_calc = tss_val
        session.tss_methode = tss_method

        return IngestResult(source_file, "imported", f"{len(points)} points, sport={sport}")


def _compute_session_tss(
    norm: dict, sport: str, points: list[dict], details: dict
) -> tuple[float | None, str | None]:
    """Charge interne (cf. core.tss). Best-effort : une ereur ici ne bloque pas
    l'import (le recalcul de masse ``scripts.recompute_tss`` reste la reference)."""
    try:
        from core.thresholds import ThresholdResolver
        from core.tss import compute_tss

        th = ThresholdResolver().seuils_for(sport, norm["date"])
        allure_nat = details.get("allure_moy_100m") if sport == Sport.natation.value else None
        return compute_tss(
            sport=sport,
            duree_s=norm["duree_s"],
            points=points,
            th=th,
            rpe=norm.get("ressenti_rpe"),
            allure_moy_s_100m=allure_nat,
        )
    except Exception:  # noqa: BLE001
        return None, None


def _upsert_daily(model, rows: list[dict], *, count_key: str) -> int:
    """Upsert merge-safe de lignes journalieres (PK = ``date``).

    Une ligne existante n'est remplacee que si la nouvelle agregation contient
    AU MOINS autant d'echantillons (``count_key``) -- evite qu'un fichier
    partiel/vide ecrase une journee deja remplie, et rend les re-scans
    idempotents.
    """
    written = 0
    with get_session() as db:
        for row in rows:
            existing = db.get(model, row["date"])
            if existing is None:
                db.add(model(**row))
                written += 1
            elif (row.get(count_key) or 0) >= (getattr(existing, count_key) or 0):
                for k, v in row.items():
                    setattr(existing, k, v)
                written += 1
    return written


def persist_daily_passive(rows: list[dict]) -> int:
    return _upsert_daily(DailyPassive, rows, count_key="n_echantillons")


def persist_sleep_daily(rows: list[dict]) -> int:
    return _upsert_daily(SleepDaily, rows, count_key="n_segments")


def persist_recovery_daily(rows: list[dict]) -> int:
    return _upsert_daily(RecoveryDaily, rows, count_key="n_echantillons")


def _process_session_group(files: dict[str, Path]) -> IngestResult:
    """Parse GPX et FIT independamment : l'echec de l'un (ex. GPX sans trace,
    frequent pour une seance renfo/gym) ne doit pas faire perdre l'autre."""
    gpx_path, fit_path = files.get(".gpx"), files.get(".fit")
    label = (gpx_path or fit_path).name

    gpx_norm = fit_norm = None
    errors: list[str] = []
    if gpx_path:
        try:
            gpx_norm = parse_gpx(gpx_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"GPX: {exc}")
    if fit_path:
        try:
            fit_norm = parse_fit(fit_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"FIT: {exc}")

    if gpx_norm is None and fit_norm is None:
        return IngestResult(label, "error", " ; ".join(errors) or "aucun fichier exploitable")

    norm = merge_normalized(gpx_norm, fit_norm)
    sport, sous_type = sport_from_filename(norm["source_file"])
    result = persist_session(norm, sport_override=sport, sous_type_override=sous_type)
    if errors and result.status == "imported":
        result.detail += f" (partiel : {' ; '.join(errors)})"
    return result


def _process_passive(path: Path) -> IngestResult:
    """Route un NDJSON passif selon le dossier parent : sleep/ recovery/ ou 24/7."""
    parents = {p.name.lower() for p in path.parents}
    try:
        if _SLEEP_DIR in parents:
            n = persist_sleep_daily(aggregate_sleep_ndjson(path))
            return IngestResult(path.name, "passive", f"sommeil : {n} jours")
        if _RECOVERY_DIR in parents:
            n = persist_recovery_daily(aggregate_recovery_ndjson(path))
            return IngestResult(path.name, "passive", f"recup : {n} jours")
        n = persist_daily_passive(aggregate_ndjson(path))
        return IngestResult(path.name, "passive", f"24/7 : {n} jours")
    except Exception as exc:  # noqa: BLE001
        return IngestResult(path.name, "error", str(exc))


def ingest_paths(
    paths: list[str | os.PathLike], *, progress: ProgressCB | None = None, limit: int | None = None
) -> list[IngestResult]:
    """Ingere un ensemble de fichiers, en regroupant FIT+GPX de meme seance.

    ``limit`` borne le nombre d'UNITES traitees (une seance = 1 unite, meme
    si elle compte 2 fichiers ; un NDJSON = 1 unite) -- utile pour un essai
    rapide sur un gros dossier. ``progress(done, total, result)`` est appele
    apres chaque unite.
    """
    clean_paths = [Path(p) for p in paths if ":" not in Path(p).name]

    groups: dict[str, dict[str, Path]] = defaultdict(dict)
    passive: list[Path] = []
    for p in clean_paths:
        ext = p.suffix.lower()
        if ext in SESSION_EXTS:
            groups[p.stem][ext] = p
        elif ext in PASSIVE_EXTS:
            passive.append(p)

    units: list[tuple] = [("session", files) for files in groups.values()]
    units += [("passive", p) for p in passive]
    if limit is not None:
        units = units[:limit]

    results: list[IngestResult] = []
    total = len(units)
    for i, (kind, payload) in enumerate(units, 1):
        result = _process_session_group(payload) if kind == "session" else _process_passive(payload)
        results.append(result)
        if progress:
            progress(i, total, result)
    return results


def ingest_file(path: str | os.PathLike) -> IngestResult:
    """Ingere un seul fichier (upload direct). Voir :func:`ingest_paths`."""
    return ingest_paths([path])[0]
