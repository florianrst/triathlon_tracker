"""Reclasse ``sport`` / ``sous_type`` des seances deja en base.

La logique de classification (``ingestion.common.sport_from_filename``) a ete
affinee : les activites a pied (marche, rando, tapis, trail) sont desormais
rattachees a ``course`` avec un ``sous_type`` explicite, le velo est ventile en
``route`` / ``vtt`` / ``home_trainer`` / ``gravel``, etc. Ce script rejoue cette
classification sur les seances existantes A PARTIR DE LEUR ``source_file`` --
sans re-importer les fichiers ni toucher aux points, au RPE ou aux notes.

Idempotent : un 2e passage ne change rien.

Usage ::

    uv run python -m scripts.reclassify_sports --dry-run   # apercu des changements
    uv run python -m scripts.reclassify_sports --yes        # applique
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from sqlalchemy import select

from core.database import get_session, init_db
from ingestion.common import sport_from_filename
from core.models import Session, Sport


def _planned_changes() -> list[tuple[int, str, str, str, str]]:
    """(id, ancien_sport, ancien_sous_type, nouveau_sport, nouveau_sous_type)."""
    changes: list[tuple[int, str, str, str, str]] = []
    with get_session() as db:
        rows = db.scalars(
            select(Session).where(Session.source_file.isnot(None)).order_by(Session.id)
        ).all()
        for s in rows:
            sport, sous_type = sport_from_filename(s.source_file)
            if sport is None:
                continue  # token inconnu : on ne devine pas
            old_sport = s.sport.value if isinstance(s.sport, Sport) else str(s.sport)
            old_sous = s.sous_type
            if old_sport == sport and old_sous == sous_type:
                continue
            changes.append((s.id, old_sport, old_sous or "—", sport, sous_type or "—"))
    return changes


def _summarize(changes: list[tuple[int, str, str, str, str]]) -> None:
    if not changes:
        print("Aucun changement : la classification en base est deja a jour.")
        return
    buckets = Counter((c[1], c[2], c[3], c[4]) for c in changes)
    print(f"{len(changes)} seance(s) a reclasser :\n")
    print(f"  {'ancien':<22} {'->':^4} {'nouveau':<22} {'count':>6}")
    print("  " + "-" * 58)
    for (os_, osub, ns, nsub), n in sorted(buckets.items(), key=lambda kv: -kv[1]):
        print(f"  {os_ + '/' + osub:<22} {'->':^4} {ns + '/' + nsub:<22} {n:>6}")
    print(
        "\nNote : seuls sport/sous_type changent. Les points GPS, le RPE, les notes\n"
        "et les tables de detail (swim/bike/run) ne sont pas touches. Une seance\n"
        "requalifiee en course/marche n'aura pas de RunDetails cree (pas d'allure\n"
        "cible pour de la marche) -- c'est voulu."
    )


def _apply(changes: list[tuple[int, str, str, str, str]]) -> int:
    ids = {c[0] for c in changes}
    written = 0
    with get_session() as db:
        for s in db.scalars(select(Session).where(Session.id.in_(ids))).all():
            sport, sous_type = sport_from_filename(s.source_file)
            if sport is None:
                continue
            s.sport = Sport(sport)
            s.sous_type = sous_type
            written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="affiche le plan, n'ecrit rien")
    parser.add_argument("--yes", action="store_true", help="applique les changements")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Rien fait : passe --dry-run pour previsualiser ou --yes pour appliquer.")
        return 1

    init_db()
    changes = _planned_changes()
    _summarize(changes)

    if args.dry_run:
        print("\n(dry-run : rien n'a ete ecrit)")
        return 0

    n = _apply(changes)
    print(f"\n✓ {n} seance(s) reclassee(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
