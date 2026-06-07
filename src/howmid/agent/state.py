"""LangGraph conversation state.

Holds the user's parsed PRs and chosen cohort so follow-ups reuse them without
re-entry ("now just my age group", "what if I trained a year") — FR-13/FR-14.
Persisted across turns by the graph's checkpointer (MemorySaver for the demo).

`prs` and `cohort` are the durable, cross-turn fields. The rest are per-turn
working values, overwritten each turn.
"""

from __future__ import annotations

from typing import TypedDict


class HowMidState(TypedDict, total=False):
    # --- per-turn input ---
    user_message: str

    # --- parse output (per turn) ---
    intent: str               # "new_prs" | "follow_up" | "what_if" | "unparseable"
    needs_clarification: bool
    clarification: str        # the question to surface when clarifying

    # --- durable, retained across turns ---
    # Parsed PRs in CANONICAL units: list of {discipline, distance_m, seconds}.
    prs: list[dict]
    # Chosen cohort filters, e.g. {"gender": "M", "age_group": "40-44"} or {} = all.
    cohort: dict

    # --- pipeline working values (per turn) ---
    extrapolations: list      # list[Extrapolation]
    percentiles: list         # list[PercentileResult]

    # --- persona / critic loop ---
    draft: str                # persona LLM's latest draft
    synth_attempts: int       # number of synthesize attempts this turn (cap = 1 retry)
    grounded: bool            # critic verdict on the latest draft
    critic_reason: str        # critic's complaint, fed back on retry

    # --- final output ---
    answer: str               # the guarded answer returned to the user
