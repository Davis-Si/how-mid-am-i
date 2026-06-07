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


_VALID_GENDERS = ("M", "F")


def _filter_clause(cohort: str | None, gender: str | None) -> tuple[str, list]:
    """Build the population filter and its bound params.

    Three mutually-exclusive cases, in priority order:
      * ``cohort`` given  → ``AND cohort = ?`` (an official cohort, e.g. 'M40-44',
        'MPRO'). A cohort label already implies a gender, so ``gender`` is ignored.
      * ``gender`` given  → ``AND gender = ?`` (the gender-only path: "all men" /
        "all women" — no age band). Validated against {'M','F'}.
      * neither           → no filter (all finishers, STAGE_3 §4B-bis).

    All values are bound parameters, never f-stringed.
    """
    if cohort is not None:
        return "AND cohort = ?", [cohort]
    if gender is not None:
        if gender not in _VALID_GENDERS:
            raise ValueError(f"gender must be one of {_VALID_GENDERS}, got {gender!r}")
        return "AND gender = ?", [gender]
    return "", []


def cohort_size(cohort: str | None, discipline: str, *, gender: str | None = None) -> int:
    """Count finishers in the population who have a non-null ``discipline`` time.

    Population is the official ``cohort`` label if given, else the gender-only
    group if ``gender`` given, else all finishers. Excludes rows whose segment
    was NULLed as an outlier upstream — this is the count the percentile engine
    ranks against.
    """
    col = _column_for(discipline)
    clause, params = _filter_clause(cohort, gender)
    sql = f"""
        SELECT count(*)
        FROM fct_results
        WHERE {col} IS NOT NULL {clause}
    """
    with read_only_connection() as con:
        return int(con.execute(sql, params).fetchone()[0])


def cohort_segment_seconds(
    cohort: str | None, discipline: str, *, gender: str | None = None
) -> list[int]:
    """Return all non-null ``discipline`` times (seconds) for the population.

    Ascending order. Empty list if the population has no usable times. See
    ``_filter_clause`` for how ``cohort`` / ``gender`` / neither select rows.
    """
    col = _column_for(discipline)
    clause, params = _filter_clause(cohort, gender)
    sql = f"""
        SELECT {col}
        FROM fct_results
        WHERE {col} IS NOT NULL {clause}
        ORDER BY {col}
    """
    with read_only_connection() as con:
        return [int(r[0]) for r in con.execute(sql, params).fetchall()]


def cohort_median_seconds(
    cohort: str | None, discipline: str, *, gender: str | None = None
) -> float | None:
    """Median ``discipline`` time (seconds) for the population, or None if empty.

    Uses DuckDB's continuous ``median`` over non-null values. See
    ``_filter_clause`` for population selection.
    """
    col = _column_for(discipline)
    clause, params = _filter_clause(cohort, gender)
    sql = f"""
        SELECT median({col})
        FROM fct_results
        WHERE {col} IS NOT NULL {clause}
    """
    with read_only_connection() as con:
        result = con.execute(sql, params).fetchone()[0]
    return None if result is None else float(result)


def cohort_rank(
    cohort: str | None,
    discipline: str,
    value_seconds: float,
    *,
    gender: str | None = None,
) -> tuple[int, int]:
    """Rank ``value_seconds`` against the population's field, computed in SQL.

    Returns ``(n_faster, cohort_n)`` where:
      * ``n_faster`` = number of field members STRICTLY FASTER than the athlete,
        i.e. ``COUNT(*) WHERE {segment} < value_seconds`` (smaller time = faster).
      * ``cohort_n`` = total finishers in the population with a non-null segment.

    The rank is count-based and computed in the database (FR-10: no LLM math,
    and no pulling 100k+ rows into Python). This function stays deliberately
    "dumb" — it returns raw counts only; ``percentile()`` owns the direction
    convention (faster = higher percentile) so that decision lives in one place.

    Population selection follows ``_filter_clause`` (cohort label, else
    gender-only, else all finishers). All values are bound parameters.
    """
    col = _column_for(discipline)
    clause, filter_params = _filter_clause(cohort, gender)
    sql = f"""
        SELECT
            count(*) FILTER (WHERE {col} < ?) AS n_faster,
            count(*) AS cohort_n
        FROM fct_results
        WHERE {col} IS NOT NULL {clause}
    """
    params = [value_seconds, *filter_params]
    with read_only_connection() as con:
        n_faster, cohort_n = con.execute(sql, params).fetchone()
    return int(n_faster), int(cohort_n)
