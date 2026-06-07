"""Deterministic unit conversion and formatting — the I/O boundary helpers.

Pure functions, NO LLM. This is where the units contract is enforced: the parse
LLM emits ``{value, unit}`` (it labels, it does not convert); these helpers turn
that into canonical **metres**, and turn canonical **seconds** back into
human-readable strings for the persona payload. Keeping the arithmetic here
(not in the LLM) is the same principle as everywhere else: the model never
computes a number.
"""

from __future__ import annotations

from howmid.config import OFFICIAL_AGE_BANDS

# Metres per unit. Distances cross into the tools layer as metres only.
_METRES_PER_UNIT = {
    "m": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "km": 1000.0,
    "k": 1000.0,        # "5k" → 5 km
    "mi": 1609.344,
    "mile": 1609.344,
    "miles": 1609.344,
    "yd": 0.9144,
    "yard": 0.9144,
    "yards": 0.9144,
}


def to_metres(value: float, unit: str) -> float:
    """Convert ``value`` in ``unit`` to metres. Raises on unknown unit / bad value."""
    key = unit.strip().lower()
    if key not in _METRES_PER_UNIT:
        raise ValueError(
            f"unknown distance unit {unit!r}; expected one of {sorted(set(_METRES_PER_UNIT))}"
        )
    if value <= 0:
        raise ValueError(f"distance value must be positive, got {value!r}")
    return value * _METRES_PER_UNIT[key]


def age_to_band(age: int) -> str:
    """Map an integer age to its official Ironman age band (e.g. 42 → '40-44').

    Returns the band WITHOUT a gender prefix (the caller prepends M/F). Raises if
    the age falls outside every official band, so out-of-range ages fail loudly
    rather than silently picking a wrong cohort.
    """
    for band in OFFICIAL_AGE_BANDS:
        lo, hi = (int(x) for x in band.split("-"))
        if lo <= age <= hi:
            return band
    raise ValueError(
        f"age {age!r} is outside the official bands "
        f"({OFFICIAL_AGE_BANDS[0]}..{OFFICIAL_AGE_BANDS[-1]})"
    )


def format_duration(seconds: float) -> str:
    """Seconds → human time. 'h:mm:ss' if ≥ 1h, else 'm:ss'.

    Rounds to the nearest second. Used to pre-format every time the persona LLM
    sees, so the model receives strings like '4:32' or '11:05:30', never raw
    seconds it might restate or mangle.
    """
    if seconds < 0:
        raise ValueError(f"seconds must be non-negative, got {seconds!r}")
    total = round(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def metres_to_km(metres: float) -> float:
    """Metres → km, for echoing a distance back to the user."""
    return metres / 1000.0
