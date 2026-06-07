"""Percentile engine: where does a value rank within the Ironman field?

Deterministic. The number path. NO LLM math (Invariant 1: this module must
never import the Anthropic SDK). The rank is computed in SQL (count-based) over
the read-only warehouse (FR-7, FR-10), filtered by cohort (FR-8), and REFUSED
with a structured signal when the cohort is below config.MIN_COHORT_SIZE (FR-9).

DIRECTION CONVENTION: faster = better. ``percentile`` is the fraction of the
field this athlete is FASTER than, scaled to 0-100 — so 90 means "faster than
90% of the field" (top 10%). Out-of-range values are reported honestly: faster
than everyone lands near 100, slower than everyone near 0. Nothing is clamped;
any "off-the-chart" messaging belongs to the agent layer, not here.

POPULATION (FR-11): the field is Ironman *finishers* — a fit, self-selected
population — never the general public. Stamped on every result via ``population``.

INPUT: ``value_seconds`` is an **Ironman-distance** time. The caller scales an
everyday PR to the Ironman distance first (``tools.extrapolation.extrapolate``);
this engine does not extrapolate.
"""

from __future__ import annotations

from dataclasses import dataclass

from howmid import config
from howmid.data import queries

# Framing string stamped on every result so the population is never ambiguous.
POPULATION = "Ironman 140.6 finishers (2002-2024, Kona-excluded)"


@dataclass(frozen=True)
class PercentileResult:
    """A grounded percentile read, or a structured insufficient-data refusal."""

    discipline: str
    value_seconds: float
    cohort_filters: dict
    percentile: float | None      # None when refused; else 0-100, faster = higher
    cohort_size: int
    cohort_median_seconds: float | None
    sufficient: bool              # False => cohort below MIN_COHORT_SIZE (FR-9)
    cohort_label: str | None = None   # resolved canonical label ('M40-44'); None = all finishers
    population: str = POPULATION      # FR-11 framing, encoded not narrated


def _resolve_cohort_label(cohort_filters: dict | None) -> str | None:
    """Map ``{gender, age_group}`` (or pro) filters to a canonical cohort label.

    Returns a label like ``'M40-44'`` or ``'MPRO'``, or ``None`` for the
    all-finishers (whole-field) comparison when no usable filter is given.

    Accepts gender as 'M'/'F' or 'Male'/'Female'. ``age_group`` may be a band
    ('40-44') or already-prefixed ('M40-44'). ``{'pro': True}`` → '{G}PRO'.
    Raises ``ValueError`` on a malformed/unknown band or gender so bad cohort
    requests fail loudly rather than silently becoming all-finishers.
    """
    if not cohort_filters:
        return None

    raw_gender = cohort_filters.get("gender")
    gender = {"male": "M", "female": "F", "m": "M", "f": "F"}.get(
        str(raw_gender).lower(), None
    ) if raw_gender is not None else None

    if cohort_filters.get("pro"):
        if gender is None:
            raise ValueError("pro cohort requires a gender ('M'/'F')")
        return f"{gender}PRO"

    age_group = cohort_filters.get("age_group")
    if age_group is None:
        # gender-only is not an official cohort in fct_results; treat absence of
        # an age band as "no cohort" rather than inventing one.
        return None

    age_group = str(age_group)
    # Allow either 'M40-44' or '40-44'.
    if age_group[:1] in ("M", "F") and "-" in age_group:
        label, band = age_group, age_group[1:]
    else:
        if gender is None:
            raise ValueError("age_group without a gender cannot form a cohort label")
        label, band = f"{gender}{age_group}", age_group

    if band not in config.OFFICIAL_AGE_BANDS:
        raise ValueError(
            f"unknown age band {band!r}; expected one of {list(config.OFFICIAL_AGE_BANDS)}"
        )
    return label


def percentile(
    discipline: str,
    value_seconds: float,
    cohort_filters: dict | None = None,
) -> PercentileResult:
    """Rank an Ironman-distance ``value_seconds`` against the field for a cohort.

    Direction: faster = higher percentile (90 ⇒ faster than 90% of the field).
    Refuses (``sufficient=False``, ``percentile=None``) when the cohort has fewer
    than ``config.MIN_COHORT_SIZE`` usable times (FR-9). Out-of-range values are
    reported as-is, never clamped.

    Framed as "vs. Ironman finishers" (FR-11) via the ``population`` field.
    """
    cohort_filters = cohort_filters or {}
    cohort_label = _resolve_cohort_label(cohort_filters)

    size = queries.cohort_size(cohort_label, discipline)
    if size < config.MIN_COHORT_SIZE:
        # Insufficient data — refuse rather than report a noisy percentile.
        return PercentileResult(
            discipline=discipline,
            value_seconds=float(value_seconds),
            cohort_filters=cohort_filters,
            percentile=None,
            cohort_size=size,
            cohort_median_seconds=None,
            sufficient=False,
            cohort_label=cohort_label,
        )

    n_faster, cohort_n = queries.cohort_rank(cohort_label, discipline, value_seconds)
    # Fraction of the field the athlete is FASTER than. Members strictly faster
    # than the athlete are ahead; the rest (incl. ties) are at-or-behind, so the
    # athlete is faster than (cohort_n - n_faster) of them.
    pct = 100.0 * (cohort_n - n_faster) / cohort_n
    median = queries.cohort_median_seconds(cohort_label, discipline)

    return PercentileResult(
        discipline=discipline,
        value_seconds=float(value_seconds),
        cohort_filters=cohort_filters,
        percentile=pct,
        cohort_size=cohort_n,
        cohort_median_seconds=median,
        sufficient=True,
        cohort_label=cohort_label,
    )
