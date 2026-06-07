"""Extrapolation engine: map an everyday PR onto Ironman-equivalent performance.

Pure Python, NO I/O, NO LLM. The model is **linear constant-pace scaling**:
``ironman_seconds = seconds * (ironman_distance / user_distance)``. The Riegel
power-law and the off-the-bike fatigue factor were explicitly deferred by the
user, so this stage does NOT use ``RIEGEL_EXPONENT`` / ``FATIGUE_FACTOR``.

UNITS CONTRACT (see STAGE_3 §3): every distance here is in **metres** and every
time in **seconds**. ``distance_m`` is assumed already converted from the user's
km/miles by the parse layer (Stage 4) — passing km here would be silently wrong
by 1000x, so we trust metres and reject obviously-bad values loudly.

Every value produced here is an ESTIMATE and is flagged as such so the agent
phrases it as a projection, never as a measured fact (FR-5).
"""

from __future__ import annotations

from dataclasses import dataclass

from howmid.config import IRONMAN_DISTANCES_M


@dataclass(frozen=True)
class Extrapolation:
    """An Ironman-distance projection of a user's PR. Always an estimate."""

    discipline: str          # 'swim' | 'bike' | 'run'
    input_distance_m: float
    input_seconds: float
    ironman_seconds: float   # projected time at the Ironman distance
    is_estimate: bool = True


def extrapolate(discipline: str, distance_m: float, seconds: float) -> Extrapolation:
    """Project a single-discipline PR onto its Ironman distance by linear scaling.

    ``ironman_seconds = seconds * (IRONMAN_DISTANCES_M[discipline] / distance_m)``.
    Both distances are metres (units contract); ``distance_m`` is the user's PR
    distance, already converted to metres by the parse layer.

    Raises ``ValueError`` on an unknown discipline or a non-positive distance/time
    (fail loudly rather than return garbage — Stage 4 owns user-input validation,
    but absurd values must never silently produce a bogus projection).
    """
    if discipline not in IRONMAN_DISTANCES_M:
        raise ValueError(
            f"unknown discipline {discipline!r}; expected one of "
            f"{sorted(IRONMAN_DISTANCES_M)}"
        )
    if distance_m <= 0:
        raise ValueError(f"distance_m must be positive metres, got {distance_m!r}")
    if seconds <= 0:
        raise ValueError(f"seconds must be positive, got {seconds!r}")

    ironman_distance_m = IRONMAN_DISTANCES_M[discipline]
    ironman_seconds = seconds * (ironman_distance_m / distance_m)
    return Extrapolation(
        discipline=discipline,
        input_distance_m=float(distance_m),
        input_seconds=float(seconds),
        ironman_seconds=ironman_seconds,
        is_estimate=True,
    )
