"""Read-only query helpers over the dbt-built marts.

This module READS the warehouse (``fct_results``) and never writes. It is the
only place the tools layer reaches the database, always through
``connection.read_only_connection``.

Discipline → column is resolved via an allowlist (``_SEGMENT_COLUMN``), never by
interpolating the caller's string into SQL: column names cannot be bound as
query parameters, so an allowlist is the safe equivalent. All *value* filters
(cohort) are passed as bound parameters.
"""

from __future__ import annotations

from howmid.data.connection import read_only_connection

# Allowlist: the only disciplines we serve, mapped to their fct_results column.
# Keys are the public discipline names; values are trusted column identifiers.
_SEGMENT_COLUMN = {
    "swim": "swim_seconds",
    "bike": "bike_seconds",
    "run": "run_seconds",
    "overall": "overall_seconds",
}


def _column_for(discipline: str) -> str:
    """Resolve a discipline to its (trusted) column name, or raise."""
    try:
        return _SEGMENT_COLUMN[discipline]
    except KeyError:
        raise ValueError(
            f"unknown discipline {discipline!r}; expected one of "
            f"{sorted(_SEGMENT_COLUMN)}"
        ) from None


def _cohort_clause(cohort: str | None) -> tuple[str, list]:
    """Build the cohort filter and its bound params.

    ``cohort=None`` means *no cohort filter* — the all-finishers (whole-field)
    comparison (STAGE_3 §4B-bis). A concrete label adds ``cohort = ?`` as a
    bound parameter (never f-stringed). Returns ``(sql_fragment, params)`` where
    the fragment is appended after the non-null segment predicate.
    """
    if cohort is None:
        return "", []
    return "AND cohort = ?", [cohort]


def cohort_size(cohort: str | None, discipline: str) -> int:
    """Count finishers in ``cohort`` who have a non-null time for ``discipline``.

    This is the count the percentile engine ranks against — so it excludes rows
    whose segment was NULLed as an outlier upstream. ``cohort`` is matched
    against the canonical ``cohort`` column (e.g. 'MPRO', 'M40-44'); ``None``
    means all finishers (no cohort filter).
    """
    col = _column_for(discipline)
    clause, params = _cohort_clause(cohort)
    sql = f"""
        SELECT count(*)
        FROM fct_results
        WHERE {col} IS NOT NULL {clause}
    """
    with read_only_connection() as con:
        return int(con.execute(sql, params).fetchone()[0])


def cohort_segment_seconds(cohort: str | None, discipline: str) -> list[int]:
    """Return all non-null ``discipline`` times (seconds) for ``cohort``.

    Ascending order. Empty list if the cohort has no usable times for the
    discipline (unknown cohort, or every value NULLed upstream). ``cohort=None``
    means all finishers.
    """
    col = _column_for(discipline)
    clause, params = _cohort_clause(cohort)
    sql = f"""
        SELECT {col}
        FROM fct_results
        WHERE {col} IS NOT NULL {clause}
        ORDER BY {col}
    """
    with read_only_connection() as con:
        return [int(r[0]) for r in con.execute(sql, params).fetchall()]


def cohort_median_seconds(cohort: str | None, discipline: str) -> float | None:
    """Median ``discipline`` time (seconds) for ``cohort``, or None if empty.

    Uses DuckDB's continuous ``median`` over non-null values. ``cohort=None``
    means all finishers.
    """
    col = _column_for(discipline)
    clause, params = _cohort_clause(cohort)
    sql = f"""
        SELECT median({col})
        FROM fct_results
        WHERE {col} IS NOT NULL {clause}
    """
    with read_only_connection() as con:
        result = con.execute(sql, params).fetchone()[0]
    return None if result is None else float(result)


def cohort_rank(
    cohort: str | None, discipline: str, value_seconds: float
) -> tuple[int, int]:
    """Rank ``value_seconds`` against the cohort's field, computed in SQL.

    Returns ``(n_faster, cohort_n)`` where:
      * ``n_faster`` = number of field members STRICTLY FASTER than the athlete,
        i.e. ``COUNT(*) WHERE {segment} < value_seconds`` (smaller time = faster).
      * ``cohort_n`` = total finishers in the cohort with a non-null segment time.

    The rank is count-based and computed in the database (FR-10: no LLM math,
    and no pulling 100k+ rows into Python). This function stays deliberately
    "dumb" — it returns raw counts only; ``percentile()`` owns the direction
    convention (faster = higher percentile) so that decision lives in one place.

    ``cohort=None`` ranks against all finishers. ``value_seconds`` and the cohort
    label are bound parameters (never f-stringed); the discipline→column name is
    resolved via the allowlist.
    """
    col = _column_for(discipline)
    clause, cohort_params = _cohort_clause(cohort)
    sql = f"""
        SELECT
            count(*) FILTER (WHERE {col} < ?) AS n_faster,
            count(*) AS cohort_n
        FROM fct_results
        WHERE {col} IS NOT NULL {clause}
    """
    params = [value_seconds, *cohort_params]
    with read_only_connection() as con:
        n_faster, cohort_n = con.execute(sql, params).fetchone()
    return int(n_faster), int(cohort_n)
