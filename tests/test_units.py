"""Unit tests for the deterministic I/O-boundary helpers (no LLM)."""

from __future__ import annotations

import pytest

from howmid.agent.units import age_to_band, format_duration, metres_to_km, to_metres


class TestToMetres:
    @pytest.mark.parametrize(
        "value,unit,expected",
        [
            (5, "km", 5000),
            (5, "k", 5000),
            (1500, "m", 1500),
            (100, "km", 100_000),
            (0.4, "km", 400),
        ],
    )
    def test_known_units(self, value, unit, expected):
        assert to_metres(value, unit) == pytest.approx(expected)

    def test_miles(self):
        assert to_metres(1, "mi") == pytest.approx(1609.344)

    def test_case_insensitive(self):
        assert to_metres(5, "KM") == 5000

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError):
            to_metres(5, "furlong")

    def test_nonpositive_raises(self):
        with pytest.raises(ValueError):
            to_metres(0, "km")
        with pytest.raises(ValueError):
            to_metres(-3, "km")


class TestAgeToBand:
    @pytest.mark.parametrize(
        "age,band",
        [(18, "18-24"), (24, "18-24"), (42, "40-44"), (44, "40-44"), (89, "85-89")],
    )
    def test_bands(self, age, band):
        assert age_to_band(age) == band

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            age_to_band(15)
        with pytest.raises(ValueError):
            age_to_band(95)


class TestFormatDuration:
    @pytest.mark.parametrize(
        "seconds,text",
        [
            (272, "4:32"),
            (90, "1:30"),
            (3600, "1:00:00"),
            (39882, "11:04:42"),
            (0, "0:00"),
        ],
    )
    def test_format(self, seconds, text):
        assert format_duration(seconds) == text

    def test_rounds(self):
        assert format_duration(271.6) == "4:32"

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            format_duration(-1)


def test_metres_to_km():
    assert metres_to_km(42195) == 42.195
    assert metres_to_km(5000) == 5.0
