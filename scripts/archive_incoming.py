"""Archive compressee, par mois, du gros export Suunto deja importe.

A lancer UNE FOIS que le contenu de la base a ete valide (page Seances /
Charge). Regroupe les fichiers de ``workouts/`` (FIT+GPX) et ``activity/``
(NDJSON) par mois AAAA-MM et ecrit un ``data/archive/AAAA-MM.tar.gz`` par
mois, puis supprime les originaux une fois chaque archive relue et verifiee.

Ne touche JAMAIS ``routes/ recovery/ sleep/ comments/ reactions/ user/`` --
ces dossiers ne sont pas parcourus, meme pour l'archivage : ils sont hors
perimetre de l'app et restent tels quels dans ``data/incoming/``.

Usage ::

    uv run python scripts/archive_incoming.py --dry-run   # aperçu
    uv run python scripts/archive_incoming.py --yes        # execute pour de vrai
"""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "data" / "incoming"
ARCHIVE_DIR = ROOT / "data" / "archive"

_SESSION_EXTS = {".fit", ".gpx"}
_PASSIVE_EXTS = {".ndjson", ".jsonl"}

_WORKOUT_MONTH_RE = re.compile(r"^(\d{4}-\d{2})-\d{2}_")
_ACTIVITY_MONTH_RE = re.compile(r"^(\d{4}-\d{2})\.")


def _month_of(path: Path) -> str | None:
    m = _WORKOUT_MONTH_RE.match(path.name) or _ACTIVITY_MONTH_RE.match(path.name)
    return m.group(1) if m else None


def _collect_by_month() -> dict[str, list[Path]]:
    by_month: dict[str, list[Path]] = defaultdict(list)
    unmatched: list[Path] = []

    for root_name, exts in (("workouts", _SESSION_EXTS), ("activity", _PASSIVE_EXTS)):
        for root in INCOMING.rglob(root_name):
            for p in root.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in exts or ":" in p.name:
                    continue
                month = _month_of(p)
                if month:
                    by_month[month].append(p)
                else:
                    unmatched.append(p)

    if unmatched:
        print(f"! {len(unmatched)} fichier(s) sans mois reconnaissable, ignores :")
        for p in unmatched[:10]:
            print("   ", p)

    return by_month


def _archive_month(month: str, files: list[Path], *, dry_run: bool) -> None:
    dest = ARCHIVE_DIR / f"{month}.tar.gz"
    if dest.exists():
        print(f"= {month} : archive deja presente ({dest.name}), ignore")
        return

    print(f"→ {month} : {len(files)} fichier(s) -> {dest.name}")
    if dry_run:
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tar:
        for p in files:
            tar.add(p, arcname=f"{month}/{p.name}")

    # verification : reouvrir l'archive et comparer le nombre de membres
    with tarfile.open(dest, "r:gz") as tar:
        n_members = len(tar.getnames())
    if n_members != len(files):
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"Verification echouee pour {month} ({n_members} != {len(files)}), archive supprimee."
        )

    for p in files:
        p.unlink()
    print(f"  ✓ verifie et originaux supprimes ({len(files)} fichiers)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="n'ecrit/ne supprime rien, affiche le plan")
    parser.add_argument("--yes", action="store_true", help="confirme l'execution reelle")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Rien fait : passe --dry-run pour previsualiser ou --yes pour executer.")
        return 1

    by_month = _collect_by_month()
    if not by_month:
        print("Aucun fichier eligible sous data/incoming/**/workouts ou **/activity.")
        return 0

    for month in sorted(by_month):
        _archive_month(month, by_month[month], dry_run=args.dry_run)

    if args.dry_run:
        print("\n(dry-run : rien n'a ete ecrit ni supprime)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
