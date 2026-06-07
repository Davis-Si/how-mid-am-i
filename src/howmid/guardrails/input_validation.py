"""Input validation (FR-2): sane time/distance ratios and plausible ranges.

Rejects physically impossible inputs (a 5-minute marathon, a 2-minute 100k)
before they reach the extrapolation/percentile path, where they would otherwise
produce a confident-but-garbage answer (e.g. a 1-second 5k → ~0s Ironman
marathon → 100th percentile). Pure math, NO LLM — this is a deterministic
backstop behind the parse LLM's own ambiguity check.

The bounds are PER-DISCIPLINE PACE bands (seconds per metre), deliberately wide:
the fast edge sits just beyond the relevant human world record so no real PR is
ever rejected, and the slow edge sits beyond a walk/easy-spin so only nonsense
(typos, joke input) trips it. They are distance-agnostic within a discipline,
which is crude at sprint distances but fine for the endurance PRs this product
takes (5k+, 40k+ bike, 1500m+ swim).
"""

from __future__ import annotations

from dataclasses import dataclass

# Plausible pace band per discipline, in SECONDS PER METRE: (fastest, slowest).
# Fastest is just beyond the human record for that discipline (impossible to
# beat); slowest is beyond a walk/easy effort (a "PR" slower than this is a typo).
#   run  : 0.13 s/m ≈ 2:10/km (just inside 1500 m WR pace) .. 1.00 s/m ≈ 16:40/km
#   bike : 0.05 s/m = 72 km/h (faster than any flat un-drafted human) .. 0.60 s/m = 6 km/h
#   swim : 0.40 s/m ≈ 40 s/100 m (inside the 100 m free WR) .. 3.00 s/m = 5:00/100 m
PACE_BOUNDS_S_PER_M = {
    "run": (0.13, 1.00),
    "bike": (0.05, 0.60),
    "swim": (0.40, 3.00),
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str | None = None
    needs_clarification: bool = False


def validate_pr(discipline: str, distance_m: float, seconds: float) -> ValidationResult:
    """Check a parsed PR for plausible pace.

    Returns ``ok=True`` for anything a real athlete could plausibly do (elite to
    very slow). Returns ``ok=False, needs_clarification=True`` with a friendly,
    specific reason when the pace is physically impossible or absurdly slow — so
    the agent asks the user to double-check rather than projecting garbage.

    Distances are metres, times seconds (the units contract). Non-positive or
    unknown-discipline inputs are rejected outright.
    """
    if discipline not in PACE_BOUNDS_S_PER_M:
        return ValidationResult(
            ok=False,
            reason=f"I only handle swim, bike, and run — not {discipline!r}.",
            needs_clarification=True,
        )
    if distance_m <= 0 or seconds <= 0:
        return ValidationResult(
            ok=False,
            reason="A PR needs a positive distance and time.",
            needs_clarification=True,
        )

    fastest, slowest = PACE_BOUNDS_S_PER_M[discipline]
    pace = seconds / distance_m  # seconds per metre

    if pace < fastest:
        return ValidationResult(
            ok=False,
            reason=(
                f"That {discipline} time looks too fast to be real — faster than "
                "the world record pace for that distance. Could you double-check it?"
            ),
            needs_clarification=True,
        )
    if pace > slowest:
        return ValidationResult(
            ok=False,
            reason=(
                f"That {discipline} time looks off — slower than a walk over that "
                "distance. Did the distance and time get swapped, or is there a typo?"
            ),
            needs_clarification=True,
        )
    return ValidationResult(ok=True)
