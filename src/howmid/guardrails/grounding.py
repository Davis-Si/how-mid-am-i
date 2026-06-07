"""Grounding guard (FR-17) and estimate-honesty guard (FR-18).

The runtime self-check: inspects the agent's DRAFT answer and rejects it unless
every percentile it states traces to a tool call made THIS turn, and every
extrapolated figure is phrased as a projection rather than a measured fact.

This is the agent evaluating its own output at runtime — distinct from the
build-time grep invariants (which check source structure) and the offline eval
harness (which scores against an external oracle).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingVerdict:
    ok: bool
    reason: str | None = None


def check_grounded(draft: str, tool_outputs: list) -> GroundingVerdict:
    """Reject any percentile in ``draft`` not supported by ``tool_outputs``."""
    raise NotImplementedError


def check_estimate_honesty(draft: str, extrapolations: list) -> GroundingVerdict:
    """Reject the draft if it asserts an estimate as a measured fact."""
    raise NotImplementedError
