"""Clean the raw Ironman CSVs into a single analysis-ready DuckDB table.

Pipeline: read 3 raw CSVs -> parse times to integer seconds -> apply documented
data-quality rules -> write `clean_results` into a DuckDB file.

Transparency model (see docs/DATA_CLEANING.md):
  * FACTS  — every count below is computed by this script and written to
             `cleaning_report.json`. No number is ever hand-typed.
  * WHY    — the rationale for each threshold lives in the comments here and in
             the doc. Re-run this script and diff the JSON to audit any change.

Modes:
  (default)   build clean_results + write cleaning_report.json
  --verify    re-assert that zero impossible values remain; exit 1 if not

Source: coachcox.co.uk/imstats. Ironman 140.6, 2002-2024, Kona-excluded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

# --- Physiological plausibility bounds (seconds) for a full 140.6 ----------
# Below the floor it isn't a real effort over the full distance (shortened /
# current-assisted course, or a timing/entry error); above the ceiling it's a
# mis-record. We NULL the offending segment, keeping the rest of the row.
SWIM_MIN, SWIM_MAX = 30 * 60, 140 * 60        # 3.8 km: 30 min .. 2h20
BIKE_MIN, BIKE_MAX = 210 * 60, 600 * 60       # 180 km: 3h30 .. 10h
RUN_MIN,  RUN_MAX = 135 * 60, 500 * 60        # 42.2 km: 2h15 .. 8h20
OVERALL_MIN, OVERALL_MAX = 420 * 60, 1140 * 60  # 7h .. 19h

ST_GEORGE_SERIES_ID = 330  # the lone World Championship race in the dataset

# Standard age-group divisions only (drop RELAY, MPC/PC para, bare M/F, etc.).
# Keep PRO as its own cohort. Pattern: M/F + two-digit age band.
AGE_GROUP_REGEX = r'^[MF][0-9]{2}-[0-9]{2}$'


# Time string -> seconds. Source uses MM:SS (1 colon) or H:MM:SS / HH:MM:SS (2).
# EDA proved 1-colon swim values are MM:SS (91% plausible that way, 0% as H:MM).
def parse_expr(col: str) -> str:
    return f"""CASE
      WHEN {col} IS NULL OR trim({col}) = '' THEN NULL
      WHEN length({col}) - length(replace({col}, ':', '')) = 1
        THEN CAST(split_part({col}, ':', 1) AS INTEGER) * 60
           + CAST(split_part({col}, ':', 2) AS INTEGER)
      WHEN length({col}) - length(replace({col}, ':', '')) = 2
        THEN CAST(split_part({col}, ':', 1) AS INTEGER) * 3600
           + CAST(split_part({col}, ':', 2) AS INTEGER) * 60
           + CAST(split_part({col}, ':', 3) AS INTEGER)
      ELSE NULL
    END"""


def stage(con: duckdb.DuckDBPyConnection, data_dir: Path) -> None:
    """Stage 1: parse raw times to seconds and join race/series metadata."""
    races = f"read_csv_auto('{data_dir}/races.csv', sample_size=-1)"
    series = f"read_csv_auto('{data_dir}/series.csv', sample_size=-1)"
    results = f"read_csv_auto('{data_dir}/results.csv', sample_size=-1, all_varchar=true)"
    sw, bk, rn, ov = (parse_expr(c) for c in ("swimTime", "bikeTime", "runTime", "overallTime"))

    con.execute(f"""
        CREATE OR REPLACE TABLE staged AS
        SELECT
            r.raceID,
            ra.seriesID,
            ra.year,
            s.location           AS series_name,
            s.continent,
            r.athleteID,
            r.Name               AS name,
            r.Country            AS country,
            r.Gender             AS gender,
            r.Division           AS division,
            r.finishStatus       AS finish_status,
            regexp_matches(r.Division, '{AGE_GROUP_REGEX}') AS is_age_group,
            upper(r.Division) IN ('MPRO', 'FPRO', 'PRO') AS is_pro,
            {ov} AS overall_seconds,
            {sw} AS swim_seconds,
            {bk} AS bike_seconds,
            {rn} AS run_seconds,
            r.overallRank  AS overall_rank,
            r.divisionRank AS division_rank
        FROM {results} r
        LEFT JOIN {races}  ra ON r.raceID = ra.id
        LEFT JOIN {series} s  ON ra.seriesID = s.id
    """)


def build(con: duckdb.DuckDBPyConnection, exclude_stgeorge: bool) -> dict:
    """Stage 2: apply cleaning rules as an attributable waterfall.

    Counts are computed sequentially — each rule's count is rows it removes from
    those that survived all prior rules — so totals never double-count.
    Returns a stats dict that becomes cleaning_report.json.
    """
    one = lambda q: con.execute(q).fetchone()[0]

    raw_rows = one("SELECT count(*) FROM staged")
    finishers = one("SELECT count(*) FROM staged WHERE finish_status = 'Finisher'")

    # Rule 1 — must be a finisher with a valid, in-bounds overall time.
    removed_bad_overall = one(f"""
        SELECT count(*) FROM staged
        WHERE finish_status = 'Finisher'
          AND (overall_seconds IS NULL
               OR overall_seconds NOT BETWEEN {OVERALL_MIN} AND {OVERALL_MAX})
    """)

    # Survivors of rule 1 (the working set for subsequent rules).
    base = f"""
        SELECT * FROM staged
        WHERE finish_status = 'Finisher'
          AND overall_seconds IS NOT NULL
          AND overall_seconds BETWEEN {OVERALL_MIN} AND {OVERALL_MAX}
    """

    # Rule 2 — exclude the St George World Championship race (keeps the
    # "regular Ironman circuit, no World Champs" population pure).
    removed_stgeorge = one(
        f"SELECT count(*) FROM ({base}) WHERE seriesID = {ST_GEORGE_SERIES_ID}"
    ) if exclude_stgeorge else 0
    st_filter = f"AND seriesID <> {ST_GEORGE_SERIES_ID}" if exclude_stgeorge else ""

    # Per-segment outliers — NULLed, not removed (the row stays usable for its
    # other valid splits). Counted among rule-1+2 survivors.
    seg_base = f"SELECT * FROM ({base}) WHERE TRUE {st_filter}"
    nulled_swim = one(f"SELECT count(*) FROM ({seg_base}) WHERE swim_seconds IS NOT NULL AND swim_seconds NOT BETWEEN {SWIM_MIN} AND {SWIM_MAX}")
    nulled_bike = one(f"SELECT count(*) FROM ({seg_base}) WHERE bike_seconds IS NOT NULL AND bike_seconds NOT BETWEEN {BIKE_MIN} AND {BIKE_MAX}")
    nulled_run = one(f"SELECT count(*) FROM ({seg_base}) WHERE run_seconds  IS NOT NULL AND run_seconds  NOT BETWEEN {RUN_MIN}  AND {RUN_MAX}")

    # Rule 3 — impossible: overall faster than the sum of all three (in-bounds)
    # splits. Evaluated on scrubbed segments (a NULLed split skips the check).
    removed_impossible = one(f"""
        WITH scrubbed AS (
            SELECT overall_seconds,
                   CASE WHEN swim_seconds BETWEEN {SWIM_MIN} AND {SWIM_MAX} THEN swim_seconds END sw,
                   CASE WHEN bike_seconds BETWEEN {BIKE_MIN} AND {BIKE_MAX} THEN bike_seconds END bk,
                   CASE WHEN run_seconds  BETWEEN {RUN_MIN}  AND {RUN_MAX}  THEN run_seconds  END rn
            FROM ({seg_base})
        )
        SELECT count(*) FROM scrubbed
        WHERE sw IS NOT NULL AND bk IS NOT NULL AND rn IS NOT NULL
          AND overall_seconds < (sw + bk + rn) - 60
    """)

    # Materialize clean_results applying rules 1-3 + segment nulling.
    con.execute(f"""
        CREATE OR REPLACE TABLE clean_results AS
        WITH scrubbed AS (
            SELECT
                raceID, seriesID, year, series_name, continent,
                athleteID, name, country, gender, division, is_age_group, is_pro,
                overall_seconds,
                CASE WHEN swim_seconds BETWEEN {SWIM_MIN} AND {SWIM_MAX} THEN swim_seconds END AS swim_seconds,
                CASE WHEN bike_seconds BETWEEN {BIKE_MIN} AND {BIKE_MAX} THEN bike_seconds END AS bike_seconds,
                CASE WHEN run_seconds  BETWEEN {RUN_MIN}  AND {RUN_MAX}  THEN run_seconds  END AS run_seconds,
                overall_rank, division_rank
            FROM ({seg_base})
        )
        SELECT * FROM scrubbed
        WHERE NOT (
            swim_seconds IS NOT NULL AND bike_seconds IS NOT NULL AND run_seconds IS NOT NULL
            AND overall_seconds < (swim_seconds + bike_seconds + run_seconds) - 60
        )
    """)
    pre_dedup = one("SELECT count(*) FROM clean_results")

    # Rule 4 — dedup (raceID, athleteID): keep the most complete row (fewest
    # NULL splits), lowest overall time as tiebreak.
    con.execute("""
        CREATE OR REPLACE TABLE clean_results AS
        SELECT * EXCLUDE (rn_) FROM (
            SELECT *, row_number() OVER (
                PARTITION BY raceID, athleteID
                ORDER BY (CASE WHEN swim_seconds IS NULL THEN 1 ELSE 0 END
                        + CASE WHEN bike_seconds IS NULL THEN 1 ELSE 0 END
                        + CASE WHEN run_seconds  IS NULL THEN 1 ELSE 0 END) ASC,
                         overall_seconds ASC
            ) rn_
            FROM clean_results
        )
        WHERE athleteID IS NULL OR rn_ = 1
    """)
    clean = one("SELECT count(*) FROM clean_results")
    removed_duplicates = pre_dedup - clean

    cov = lambda c: one(f"SELECT count(*) FROM clean_results WHERE {c} IS NOT NULL")
    return {
        "source": "coachcox.co.uk/imstats — Ironman 140.6, 2002-2024, Kona-excluded",
        "exclude_st_george": exclude_stgeorge,
        "thresholds_seconds": {
            "swim": [SWIM_MIN, SWIM_MAX], "bike": [BIKE_MIN, BIKE_MAX],
            "run": [RUN_MIN, RUN_MAX], "overall": [OVERALL_MIN, OVERALL_MAX],
        },
        "counts": {
            "raw_result_rows": raw_rows,
            "finishers_preclean": finishers,
            "clean_finishers_kept": clean,
        },
        "rows_removed": {
            "missing_or_oob_overall": removed_bad_overall,
            "st_george_world_champ": removed_stgeorge,
            "overall_less_than_splits": removed_impossible,
            "duplicate_athlete_race": removed_duplicates,
            "non_finishers": raw_rows - finishers,
        },
        "segments_nulled": {
            "swim": nulled_swim, "bike": nulled_bike, "run": nulled_run,
        },
        "segment_coverage": {
            "swim": cov("swim_seconds"), "bike": cov("bike_seconds"),
            "run": cov("run_seconds"), "age_group": one("SELECT count(*) FROM clean_results WHERE is_age_group"),
        },
    }


# Invariants that must hold on clean_results. Each returns rows that VIOLATE it.
VERIFY_CHECKS = {
    "swim_in_bounds": f"swim_seconds IS NOT NULL AND swim_seconds NOT BETWEEN {SWIM_MIN} AND {SWIM_MAX}",
    "bike_in_bounds": f"bike_seconds IS NOT NULL AND bike_seconds NOT BETWEEN {BIKE_MIN} AND {BIKE_MAX}",
    "run_in_bounds": f"run_seconds IS NOT NULL AND run_seconds NOT BETWEEN {RUN_MIN} AND {RUN_MAX}",
    "overall_in_bounds": f"overall_seconds NOT BETWEEN {OVERALL_MIN} AND {OVERALL_MAX}",
    "overall_ge_splits": "swim_seconds IS NOT NULL AND bike_seconds IS NOT NULL AND run_seconds IS NOT NULL AND overall_seconds < swim_seconds+bike_seconds+run_seconds-60",
    "no_st_george": f"seriesID = {ST_GEORGE_SERIES_ID}",
    "finishers_only": "overall_seconds IS NULL",
}


def verify(con: duckdb.DuckDBPyConnection) -> int:
    """Re-assert cleaning invariants. Returns process exit code (0 = all pass)."""
    try:
        con.execute("SELECT 1 FROM clean_results LIMIT 1")
    except duckdb.CatalogException:
        print("VERIFY FAILED: clean_results does not exist. Run the cleaner first.")
        return 1

    failures = 0
    print("VERIFY clean_results")
    for name, violation in VERIFY_CHECKS.items():
        bad = con.execute(f"SELECT count(*) FROM clean_results WHERE {violation}").fetchone()[0]
        ok = bad == 0
        failures += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:<22} violations={bad}")
    dup = con.execute("""
        SELECT count(*) FROM (
            SELECT raceID, athleteID FROM clean_results
            WHERE athleteID IS NOT NULL GROUP BY 1,2 HAVING count(*) > 1)
    """).fetchone()[0]
    failures += 0 if dup == 0 else 1
    print(f"  [{'PASS' if dup == 0 else 'FAIL'}] {'unique_athlete_race':<22} violations={dup}")

    print("ALL CHECKS PASSED" if failures == 0 else f"{failures} CHECK(S) FAILED")
    return 0 if failures == 0 else 1


def print_report(stats: dict) -> None:
    c, rm, cov = stats["counts"], stats["rows_removed"], stats["segment_coverage"]
    kept = c["clean_finishers_kept"]
    print("\n" + "=" * 62)
    print("CLEANING REPORT")
    print("=" * 62)
    print(f"  raw result rows .................. {c['raw_result_rows']:>10,}")
    print(f"  finishers (pre-clean) ............ {c['finishers_preclean']:>10,}")
    print("  rows removed:")
    for k, v in rm.items():
        print(f"    - {k:<28} {v:>10,}")
    print("  segments NULLed (row kept):")
    for k, v in stats["segments_nulled"].items():
        print(f"    - {k:<28} {v:>10,}")
    print(f"  clean finishers (kept) ........... {kept:>10,}")
    for seg in ("swim", "bike", "run", "age_group"):
        print(f"    with valid {seg:<10} ......... {cov[seg]:>10,}  ({100*cov[seg]/kept:.1f}%)")
    print("=" * 62)


def main() -> None:
    ap = argparse.ArgumentParser(description="Clean Ironman CSVs into DuckDB.")
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--db", type=Path, default=Path("data/howmid.duckdb"))
    ap.add_argument("--report", type=Path, default=Path("data/cleaning_report.json"),
                    help="path to write the machine-readable cleaning report")
    ap.add_argument("--keep-stgeorge", action="store_true",
                    help="keep the St George World Championship race (default: exclude)")
    ap.add_argument("--verify", action="store_true",
                    help="only re-assert invariants on an existing clean_results; exit 1 on any failure")
    args = ap.parse_args()

    if args.verify:
        con = duckdb.connect(str(args.db), read_only=True)
        try:
            sys.exit(verify(con))
        finally:
            con.close()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.db))
    try:
        stage(con, args.data)
        stats = build(con, exclude_stgeorge=not args.keep_stgeorge)
        print_report(stats)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(stats, indent=2))
        print(f"\nWrote clean_results to {args.db}")
        print(f"Wrote cleaning report to {args.report}")
        code = verify(con)
        sys.exit(code)
    finally:
        con.close()


if __name__ == "__main__":
    main()
