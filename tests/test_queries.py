"""Tests for the read-only query helpers.

Ground truth is read from ``data/cohort_sizing.json`` (produced by
scripts/cohort_sizing.py) rather than hard-typed, so the tests track the data.
The sizing JSON records per-segment coverage per age-group cell, so for those
cells we assert the query returns *exactly* the recorded count.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from howmid.config import MIN_COHORT_SIZE
from howmid.data import queries

SIZING = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "cohort_sizing.json").read_text()
)
MATRIX = SIZING["age_group_matrix"]
PRO = SIZING["pro"]


def test_unknown_discipline_raises():
    with pytest.raises(ValueError):
        queries.cohort_size("M40-44", "marathon")


def test_pro_cohort_size_consistent_with_sizing():
    """MPRO run count is >0 and <= the cohort total (segment may be NULLed)."""
    total = PRO["MPRO"]                       # 8678
    n_run = queries.cohort_size("MPRO", "run")
    assert 0 < n_run <= total


@pytest.mark.parametrize("gender,band,discipline", [
    ("M", "40-44", "run"),    # the largest cell
    ("F", "30-34", "swim"),
    ("M", "25-29", "bike"),
])
def test_age_group_size_matches_recorded_coverage(gender, band, discipline):
    """cohort_size equals the per-segment coverage recorded in the sizing JSON."""
    cohort = f"{gender}{band}"
    expected = MATRIX[gender][band][discipline]
    assert queries.cohort_size(cohort, discipline) == expected


def test_age_group_cell_is_nonempty():
    assert queries.cohort_size("M40-44", "overall") > 0


def test_submin_cohort_is_below_threshold():
    """A known sub-minimum cell (F75-79) returns a count below MIN_COHORT_SIZE."""
    assert MATRIX["F"]["75-79"]["meets_min"] is False   # ground-truth sanity
    n = queries.cohort_size("F75-79", "overall")
    assert 0 < n < MIN_COHORT_SIZE


def test_unknown_cohort_returns_zero_and_empty():
    assert queries.cohort_size("NOT_A_COHORT", "run") == 0
    assert queries.cohort_segment_seconds("NOT_A_COHORT", "run") == []
    assert queries.cohort_median_seconds("NOT_A_COHORT", "run") is None


def test_segment_seconds_sorted_and_in_bounds():
    secs = queries.cohort_segment_seconds("M40-44", "swim")
    assert len(secs) > 0
    assert secs == sorted(secs)
    # all within the cleaner's swim bounds (30min..2h20)
    assert all(1800 <= s <= 8400 for s in secs)


def test_median_matches_manual_midpoint():
    """The helper's median agrees with the midpoint of the sorted segment list."""
    secs = queries.cohort_segment_seconds("F40-44", "run")
    med = queries.cohort_median_seconds("F40-44", "run")
    assert med is not None
    n = len(secs)
    manual = secs[n // 2] if n % 2 else (secs[n // 2 - 1] + secs[n // 2]) / 2
    assert med == pytest.approx(manual, abs=1.0)
