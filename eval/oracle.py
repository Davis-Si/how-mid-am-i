"""Independent pandas oracle for the percentile tool (FR-21, seed of the harness).

This recomputes the same percentile the production tool returns, but by a
DELIBERATELY DIFFERENT route: it pulls the cohort's raw segment times into a
pandas Series and ranks in Python, rather than going through
``howmid.tools.percentile`` / ``howmid.data.queries``. If the two agree, the
SQL-side count logic is corroborated by an independent implementation.

Kept intentionally minimal — just enough to verify the tool. The full eval
harness (cases, report, version tracking) is a later stage.

NOTE: this is test/eval scaffolding, not the number path — it may use pandas
freely. The production tool still computes its rank in SQL (FR-10).
"""

from __future__ import annotations

import duckdb
import pandas as pd

from howmid import config

# Same direction convention as tools.percentile: faster = higher percentile,
# = fraction of the field the athlete is faster than, scaled to 0-100.
_SEGMENT_COLUMN = {
    "swim": "swim_seconds",
    "bike": "bike_seconds",
    "run": "run_seconds",
    "overall": "overall_seconds",
}


def _load_segment(cohort: str | None, discipline: str) -> pd.Series:
    """Load all non-null segment times for the cohort straight from DuckDB."""
    col = _SEGMENT_COLUMN[discipline]
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    try:
        if cohort is None:
            df = con.execute(
                f"SELECT {col} AS s FROM fct_results WHERE {col} IS NOT NULL"
            ).df()
        else:
            df = con.execute(
                f"SELECT {col} AS s FROM fct_results "
                f"WHERE {col} IS NOT NULL AND cohort = ?",
                [cohort],
            ).df()
    finally:
        con.close()
    return df["s"]


def oracle_percentile(
    cohort: str | None, discipline: str, value_seconds: float
) -> dict:
    """Independently compute the percentile for ``value_seconds`` in ``cohort``.

    Returns ``{percentile, cohort_size, median, sufficient}``. ``percentile`` is
    ``None`` when the cohort is below ``config.MIN_COHORT_SIZE`` (mirrors the
    tool's refusal), else the fraction faster than, in 0-100.
    """
    s = _load_segment(cohort, discipline)
    n = int(s.size)
    if n < config.MIN_COHORT_SIZE:
        return {"percentile": None, "cohort_size": n, "median": None, "sufficient": False}

    n_faster = int((s < value_seconds).sum())   # field members strictly faster
    pct = 100.0 * (n - n_faster) / n
    return {
        "percentile": pct,
        "cohort_size": n,
        "median": float(s.median()),
        "sufficient": True,
    }
