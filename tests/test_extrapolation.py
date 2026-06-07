"""Tests for the linear extrapolation model (pure math, no DB)."""

from __future__ import annotations

import pytest

from howmid.config import IRONMAN_DISTANCES_M
from howmid.tools.extrapolation import extrapolate


def test_run_5k_hand_computed():
    """25:00 over 5000 m → run Ironman projection = 1500 s × 42195/5000."""
    e = extrapolate("run", 5000, 25 * 60)
    assert e.ironman_seconds == pytest.approx(25 * 60 * 42195 / 5000)
    assert e.is_estimate is True
    assert e.discipline == "run"


@pytest.mark.parametrize("discipline,distance_m,seconds", [
    ("swim", 1500, 30 * 60),     # 1500 m swim in 30:00
    ("bike", 40_000, 75 * 60),   # 40 km TT in 1:15
    ("run", 10_000, 50 * 60),    # 10 k in 50:00
])
def test_linear_scaling_all_disciplines(discipline, distance_m, seconds):
    e = extrapolate(discipline, distance_m, seconds)
    expected = seconds * (IRONMAN_DISTANCES_M[discipline] / distance_m)
    assert e.ironman_seconds == pytest.approx(expected)


@pytest.mark.parametrize("discipline", ["swim", "bike", "run"])
def test_round_trip_scale_up_then_down(discipline):
    """Scaling a PR up to Ironman then back to the original distance is identity."""
    distance_m, seconds = 10_000 if discipline != "swim" else 1500, 40 * 60
    up = extrapolate(discipline, distance_m, seconds)
    # scale the Ironman projection back down to the original distance
    back = up.ironman_seconds * (distance_m / IRONMAN_DISTANCES_M[discipline])
    assert back == pytest.approx(seconds)


def test_unknown_discipline_raises():
    with pytest.raises(ValueError):
        extrapolate("triathlon", 5000, 1500)


@pytest.mark.parametrize("distance_m,seconds", [(0, 1500), (-5000, 1500), (5000, 0), (5000, -1)])
def test_non_positive_inputs_raise(distance_m, seconds):
    with pytest.raises(ValueError):
        extrapolate("run", distance_m, seconds)
