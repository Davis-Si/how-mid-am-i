"""Input validation (FR-2): sane time/distance ratios and plausible ranges.

Rejects physically impossible inputs (a 5-minute marathon, a 2-minute 100k)
and signals when input is ambiguous so the agent asks a clarifying question
rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str | None = None
    needs_clarification: bool = False


def validate_pr(discipline: str, distance_m: float, seconds: float) -> ValidationResult:
    """Check a parsed PR for plausible pace; flag implausible or ambiguous input."""
    raise NotImplementedError
