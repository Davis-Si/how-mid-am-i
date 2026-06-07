"""Tests for the percentile engine — verified against the independent oracle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.oracle import oracle_percentile
from howmid.config import MIN_COHORT_SIZE
from howmid.data import queries
from howmid.tools.percentile import percentile

SIZING = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "cohort_sizing.json").read_text()
)


@pytest.mark.parametrize("cohort,filt,discipline", [
    ("M40-44", {"gender": "M", "age_group": "40-44"}, "run"),
    ("MPRO", {"gender": "M", "pro": True}, "bike"),
    ("F30-34", {"gender": "F", "age_group": "30-34"}, "swim"),
])
def test_tool_matches_oracle(cohort, filt, discipline):
    """The SQL tool agrees with the independent pandas oracle (FR-21)."""
    value = queries.cohort_median_seconds(cohort, discipline)  # a real, central value
    tool = percentile(discipline, value, filt)
    orc = oracle_percentile(cohort, discipline, value)
    assert tool.sufficient is orc["sufficient"]
    assert tool.percentile == pytest.approx(orc["percentile"], abs=1e-6)
    assert tool.cohort_size == orc["cohort_size"]


def test_all_finishers_matches_oracle():
    """cohort_filters=None ranks against the whole field, agreeing with oracle."""
    value = 14_000.0
    tool = percentile("run", value, None)
    orc = oracle_percentile(None, "run", value)
    assert tool.cohort_label is None
    assert tool.percentile == pytest.approx(orc["percentile"], abs=1e-6)


def test_refusal_on_sub_min_cohort():
    """A known sub-MIN_COHORT_SIZE cell (F75-79) refuses (FR-9)."""
    assert SIZING["age_group_matrix"]["F"]["75-79"]["meets_min"] is False
    r = percentile("run", 16_000, {"gender": "F", "age_group": "75-79"})
    assert r.sufficient is False
    assert r.percentile is None
    assert 0 < r.cohort_size < MIN_COHORT_SIZE
    assert r.cohort_median_seconds is None


def test_direction_fast_high_slow_low():
    """Faster time → higher percentile; slower → lower. Pins the convention."""
    fast = percentile("run", 8_000, {"gender": "M", "age_group": "40-44"})    # ~2h13
    slow = percentile("run", 28_000, {"gender": "M", "age_group": "40-44"})   # ~7h47
    assert fast.percentile > slow.percentile
    assert fast.percentile > 90
    assert slow.percentile < 10


def test_out_of_range_not_clamped():
    """Faster than the whole cohort → ~100; slower than all → ~0. No clamping/error."""
    secs = queries.cohort_segment_seconds("M40-44", "run")
    faster_than_all = secs[0] - 1
    slower_than_all = secs[-1] + 1
    top = percentile("run", faster_than_all, {"gender": "M", "age_group": "40-44"})
    bot = percentile("run", slower_than_all, {"gender": "M", "age_group": "40-44"})
    assert top.percentile == pytest.approx(100.0)
    assert bot.percentile == pytest.approx(0.0, abs=0.01)


def test_population_framing_present():
    """FR-11: every result carries the finisher-population framing."""
    r = percentile("run", 14_000, {"gender": "M", "age_group": "40-44"})
    assert "finisher" in r.population.lower()


def test_bad_age_band_raises():
    with pytest.raises(ValueError):
        percentile("run", 14_000, {"gender": "M", "age_group": "33-37"})
