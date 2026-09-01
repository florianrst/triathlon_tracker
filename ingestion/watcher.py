"""Scan du dossier surveille pour ingestion.

Choix acte avec l'utilisateur : PAS de process background / watchdog pour
l'instant, juste un scan a la demande declenche depuis l'UI (bouton
"Scanner le dossier") ou en ligne de commande ::

    uv run python -m ingestion.watcher

Seuls les sous-dossiers ``workouts/`` (FIT + GPX), ``activity/`` (NDJSON 24/7),
``sleep/`` (NDJSON sommeil) et ``recovery/`` (NDJSON recuperation/stress) d'un
export Suunto sont parcourus -- en limitant les racines explorees, plutot
qu'en excluant des noms, pour ne jamais ingerer par accident ``routes/``
(parcours planifies, pas des seances), ``comments/``, ``reactions/`` ou
``user/`` (hors perimetre de l'app). Si le dossier surveille n'a pas cette
arborescence (ex. fichiers deposes a plat), on retombe sur un scan de la racine
elle-meme.

Le dedoublonnage se fait au niveau de :func:`ingestion.persist.ingest_paths`
(sur ``source_file``/``source_key`` en base) ; un re-scan est donc sans
risque, meme partiel (``limit``).
"""

from __future__ import annotations

from pathlib import Path

from database import INCOMING_DIR
from .persist import PASSIVE_EXTS, ProgressCB, SESSION_EXTS, IngestResult, ingest_paths

_KNOWN_EXTS = set(SESSION_EXTS) | set(PASSIVE_EXTS)
_SESSION_SUBDIR = "workouts"
_PASSIVE_SUBDIRS = ("activity", "sleep", "recovery")


def eligible_paths(directory: Path) -> list[Path]:
    session_roots = list(directory.rglob(_SESSION_SUBDIR))
    passive_roots = [r for sub in _PASSIVE_SUBDIRS for r in directory.rglob(sub)]

    paths: list[Path] = []
    if session_roots or passive_roots:
        for root in session_roots:
            paths += [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SESSION_EXTS]
        for root in passive_roots:
            paths += [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in PASSIVE_EXTS]
    else:
        # pas d'arborescence Suunto connue : on scanne la racine elle-meme
        # (cas des uploads/depots a plat dans data/incoming/)
        paths = [p for p in directory.rglob("*") if p.is_file() and p.suffix.lower() in _KNOWN_EXTS]

    return sorted(set(paths))


def scan_incoming(
    directory: str | Path | None = None, *, progress: ProgressCB | None = None, limit: int | None = None
) -> list[IngestResult]:
    """Ingere les fichiers eligibles du dossier surveille. Idempotent."""
    directory = Path(directory) if directory else INCOMING_DIR
    directory.mkdir(parents=True, exist_ok=True)

    paths = eligible_paths(directory)
    return ingest_paths(paths, progress=progress, limit=limit)


def main() -> None:  # pragma: no cover
    from collections import Counter

    from database import init_db

    init_db()
    results = scan_incoming()
    if not results:
        print("Aucun fichier a traiter dans", INCOMING_DIR)
        return

    counts = Counter(r.status for r in results)
    print("Resume :", dict(counts))
    for r in results:
        if r.status == "error":
            print(f"[erreur] {Path(r.path).name} : {r.detail}")


if __name__ == "__main__":  # pragma: no cover
    main()
