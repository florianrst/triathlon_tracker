"""(Re)calcule ``tss_calc`` / ``tss_methode`` de toutes les seances.

Charge interne, INDEPENDANTE de la montre (module ``core.tss``). A relancer :
- apres un gros import ;
- apres avoir saisi / modifie des seuils (page Tests & zones) -- le hrTSS,
  rTSS, sTSS, pTSS utilisent alors tes vraies valeurs au lieu des defauts.

Usage ::

    uv run python -m scripts.recompute_tss --dry-run   # repartition des methodes
    uv run python -m scripts.recompute_tss --yes        # ecrit en base
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from sqlalchemy import select

from core.database import get_session, init_db
from core.models import Session, SessionPoint, SwimDetails
from core.thresholds import ThresholdResolver
from core.tss import compute_tss

_BATCH = 200


def _points_for(db, session_id: int) -> list[dict]:
    rows = db.execute(
        select(
            SessionPoint.t_offset_s,
            SessionPoint.hr,
            SessionPoint.vitesse,
            SessionPoint.puissance,
            SessionPoint.distance_cum_m,
        )
        .where(SessionPoint.session_id == session_id)
        .order_by(SessionPoint.t_offset_s)
    ).all()
    return [
        {"t_offset_s": r.t_offset_s, "hr": r.hr, "vitesse": r.vitesse,
         "puissance": r.puissance, "distance_cum_m": r.distance_cum_m}
        for r in rows
    ]


def run(*, write: bool) -> Counter:
    resolver = ThresholdResolver()
    methods: Counter = Counter()

    with get_session() as db:
        ids = [row[0] for row in db.execute(select(Session.id).order_by(Session.id)).all()]

        for start in range(0, len(ids), _BATCH):
            batch = ids[start : start + _BATCH]
            for s in db.scalars(select(Session).where(Session.id.in_(batch))).all():
                sport = s.sport.value if hasattr(s.sport, "value") else str(s.sport)
                allure_nat = None
                if sport == "natation":
                    sd = db.get(SwimDetails, s.id)
                    allure_nat = sd.allure_moy_100m if sd else None

                th = resolver.seuils_for(sport, s.date)
                pts = _points_for(db, s.id)
                tss_val, method = compute_tss(
                    sport=sport,
                    duree_s=s.duree_s,
                    points=pts,
                    th=th,
                    rpe=s.ressenti_rpe,
                    allure_moy_s_100m=allure_nat,
                )
                methods[method or "aucune"] += 1
                if write:
                    s.tss_calc = tss_val
                    s.tss_methode = method
            if not write:
                db.expunge_all()

    return methods


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="affiche la repartition, n'ecrit rien")
    parser.add_argument("--yes", action="store_true", help="ecrit tss_calc / tss_methode en base")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Rien fait : passe --dry-run pour previsualiser ou --yes pour ecrire.")
        return 1

    init_db()
    methods = run(write=args.yes)

    total = sum(methods.values())
    print(f"{total} seance(s) traitee(s). Repartition des methodes :\n")
    for method, n in methods.most_common():
        print(f"  {method:<8} {n:>5}  ({100 * n / total:.0f} %)")
    if args.dry_run:
        print("\n(dry-run : rien n'a ete ecrit)")
    else:
        print("\n✓ tss_calc / tss_methode ecrits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
