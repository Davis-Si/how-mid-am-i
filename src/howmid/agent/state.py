"""LangGraph conversation state.

Holds the user's parsed PRs so follow-ups reuse them without re-entry
("now just my age group", "what if I trained a year") — FR-13/FR-14. Persisted
across turns by the graph's checkpointer.
"""

from __future__ import annotations

from typing import TypedDict


class HowMidState(TypedDict, total=False):
    # Raw turn input.
    user_message: str
    # Parsed PRs: list of {discipline, distance_m, seconds}. Retained across turns.
    prs: list[dict]
    # Outputs threaded through the pipeline.
    extrapolations: list  # list[Extrapolation]
    percentiles: list     # list[PercentileResult]
    # The persona-rendered draft, and the final guarded answer.
    draft: str
    answer: str
    # Set when input is ambiguous/implausible (routes to a clarifying question).
    needs_clarification: bool
    clarification: str
