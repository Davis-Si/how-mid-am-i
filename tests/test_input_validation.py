"""Tests for the deterministic pace-plausibility guard (FR-2, no LLM)."""

from __future__ import annotations

import pytest

from howmid.guardrails.input_validation import validate_pr


@pytest.mark.parametrize("discipline,distance_m,seconds", [
    ("run", 5000, 1500),       # 25:00 5k — everyday
    ("run", 5000, 755),        # ~12:35 5k — world record, must still pass
    ("run", 42195, 7235),      # ~2:00:35 marathon WR
    ("run", 42195, 21600),     # 6:00 marathon — slow but real
    ("bike", 40000, 4500),     # 40k TT in 1:15
    ("bike", 56000, 3600),     # ~hour record, must pass
    ("swim", 1500, 1800),      # 30:00 1500m
    ("swim", 100, 47),         # ~100m free WR, must pass
])
def test_accepts_real_prs_including_world_records(discipline, distance_m, seconds):
    assert validate_pr(discipline, distance_m, seconds).ok is True


@pytest.mark.parametrize("discipline,distance_m,seconds", [
    ("run", 5000, 1),          # 1-second 5k
    ("run", 42195, 120),       # 2-minute marathon
    ("bike", 100000, 120),     # 100k in 2 minutes
    ("swim", 3800, 300),       # 3.8k swim in 5 minutes
])
def test_rejects_impossibly_fast(discipline, distance_m, seconds):
    r = validate_pr(discipline, distance_m, seconds)
    assert r.ok is False
    assert r.needs_clarification is True
    assert r.reason


def test_rejects_impossibly_slow():
    # a "5k" that took 3 hours — slower than a walk, likely a swapped/typo entry
    r = validate_pr("run", 5000, 3 * 3600)
    assert r.ok is False and r.needs_clarification is True


@pytest.mark.parametrize("bad", [(0, 1500), (-5000, 1500), (5000, 0), (5000, -1)])
def test_rejects_nonpositive(bad):
    assert validate_pr("run", bad[0], bad[1]).ok is False


def test_rejects_unknown_discipline():
    assert validate_pr("triathlon", 5000, 1500).ok is False
