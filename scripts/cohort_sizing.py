"""Cohort sizing against the official Ironman age-group structure.

Ironman's official competition cohorts are: PRO (M/F), and 5-year age-group
bands by gender from 18-24 up to 85-89. This script normalizes the raw
`division` field to those canonical cohorts, reports how cleanly the data
traces to them, and sizes every (gender x age-group) cell — flagging which
clear the minimum-sample threshold the percentile engine requires (FR-9).

Read-only: queries clean_results, writes cohort_sizing.json. No mutation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

# Single source of truth — the official bands and the min-cohort threshold live
# in the package config, not here, so the sizing script and the percentile
# engine can never disagree on what a valid cohort is.
from howmid.config import COHORT_GENDERS, MIN_COHORT_SIZE, OFFICIAL_AGE_BANDS

OFFICIAL_BANDS = list(OFFICIAL_AGE_BANDS)
MIN_COHORT = MIN_COHORT_SIZE


# Map raw division -> canonical cohort. A division is a valid official cohort
# only if it is an exact gender+band match or {M,F}PRO. Everything else
# (RELAY, PARA codes, bare M/F, country codes, scrape junk, non-standard
# aggregate bands like M70-99) is bucketed as NOT an official cohort.
def cohort_case_sql() -> str:
    official = []
    for g in COHORT_GENDERS:
        for b in OFFICIAL_AGE_BANDS:
            official.append(f"'{g}{b}'")
    official_list = ", ".join(official)
    return f"""
        CASE
            WHEN division IN ('MPRO', 'FPRO') THEN division
            WHEN division IN ({official_list}) THEN division
            ELSE NULL
        END
    """


def size(con: duckdb.DuckDBPyConnection) -> dict:
    cohort = cohort_case_sql()
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE c AS
        SELECT *, ({cohort}) AS cohort,
               CASE WHEN ({cohort}) IS NULL THEN FALSE ELSE TRUE END AS is_official
        FROM clean_results
    """)

    one = lambda q: con.execute(q).fetchone()[0]
    total = one("SELECT count(*) FROM c")
    official = one("SELECT count(*) FROM c WHERE is_official")
    pro = one("SELECT count(*) FROM c WHERE cohort IN ('MPRO','FPRO')")
    ag = official - pro

    # Per-cohort sizes (age groups only; PRO reported separately).
    ag_rows = con.execute(f"""
        SELECT
            substr(cohort, 1, 1) AS gender,
            substr(cohort, 2)    AS band,
            count(*)             AS n,
            -- segment coverage within the cohort: how many have each split
            count(swim_seconds)  AS n_swim,
            count(bike_seconds)  AS n_bike,
            count(run_seconds)   AS n_run
        FROM c
        WHERE is_official AND cohort NOT IN ('MPRO','FPRO')
        GROUP BY 1, 2
    """).fetchall()

    # Build a gender x band matrix in official band order.
    matrix = {"M": {}, "F": {}}
    for gender, band, n, n_sw, n_bk, n_rn in ag_rows:
        matrix[gender][band] = {
            "n": n, "swim": n_sw, "bike": n_bk, "run": n_rn,
            "meets_min": n >= MIN_COHORT,
        }

    pro_rows = {r[0]: r[1] for r in con.execute(
        "SELECT cohort, count(*) FROM c WHERE cohort IN ('MPRO','FPRO') GROUP BY 1"
    ).fetchall()}

    # What didn't map — for the transparency report.
    unmapped = con.execute("""
        SELECT division, count(*) c FROM c WHERE NOT is_official
        GROUP BY 1 ORDER BY c DESC LIMIT 20
    """).fetchall()

    return {
        "min_cohort_threshold": MIN_COHORT,
        "totals": {
            "clean_finishers": total,
            "official_cohort": official,
            "official_pct": round(100 * official / total, 2),
            "age_group": ag,
            "pro": pro,
            "unmapped": total - official,
        },
        "pro": pro_rows,
        "age_group_matrix": matrix,
        "cells_meeting_min": sum(
            1 for g in matrix for b in matrix[g] if matrix[g][b]["meets_min"]
        ),
        "cells_total": sum(len(matrix[g]) for g in matrix),
        "unmapped_top": [{"division": d, "n": n} for d, n in unmapped],
    }


def print_report(s: dict) -> None:
    t = s["totals"]
    print("\n" + "=" * 64)
    print("OFFICIAL IRONMAN COHORT SIZING")
    print("=" * 64)
    print(f"  clean finishers .............. {t['clean_finishers']:>10,}")
    print(f"  trace to official cohort ..... {t['official_cohort']:>10,}  ({t['official_pct']}%)")
    print(f"    - age-group .............. {t['age_group']:>10,}")
    print(f"    - PRO .................... {t['pro']:>10,}  (M {s['pro'].get('MPRO',0):,} / F {s['pro'].get('FPRO',0):,})")
    print(f"  not an official cohort ....... {t['unmapped']:>10,}  (RELAY/PARA/bare M-F/junk)")

    print(f"\n  Age-group matrix (n; * = below min {s['min_cohort_threshold']}):")
    M, F = s["age_group_matrix"]["M"], s["age_group_matrix"]["F"]
    print(f"  {'band':<8}{'Male':>12}{'Female':>12}")
    for b in OFFICIAL_BANDS:
        m = M.get(b); f = F.get(b)
        mv = f"{m['n']:,}{'' if not m or m['meets_min'] else '*'}" if m else "—"
        fv = f"{f['n']:,}{'' if not f or f['meets_min'] else '*'}" if f else "—"
        print(f"  {b:<8}{mv:>12}{fv:>12}")
    print(f"\n  cells meeting min: {s['cells_meeting_min']}/{s['cells_total']}")
    print("=" * 64)


def main() -> None:
    ap = argparse.ArgumentParser(description="Official Ironman cohort sizing.")
    ap.add_argument("--db", type=Path, default=Path("data/howmid.duckdb"))
    ap.add_argument("--out", type=Path, default=Path("data/cohort_sizing.json"))
    args = ap.parse_args()

    con = duckdb.connect(str(args.db), read_only=True)
    try:
        stats = size(con)
        print_report(stats)
        args.out.write_text(json.dumps(stats, indent=2))
        print(f"\nWrote {args.out}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
