"""Graph nodes: parse -> extrapolate -> compare -> synthesize -> critic.

A linear pipeline with conditional edges (not an LLM supervisor). Only the
parse and synthesize nodes touch the LLM (via howmid.llm); extrapolate and
compare call the deterministic tools. The critic node runs the runtime
guardrails over the draft before it becomes the answer.
"""

from __future__ import annotations

from howmid.agent.state import HowMidState


def parse_node(state: HowMidState) -> HowMidState:        # LLM: structured parse (FR-1)
    raise NotImplementedError


def extrapolate_node(state: HowMidState) -> HowMidState:  # tools.extrapolation (no LLM)
    raise NotImplementedError


def compare_node(state: HowMidState) -> HowMidState:      # tools.percentile (no LLM)
    raise NotImplementedError


def synthesize_node(state: HowMidState) -> HowMidState:   # LLM: persona delivery (FR-15)
    raise NotImplementedError


def critic_node(state: HowMidState) -> HowMidState:       # guardrails.grounding (FR-17/18)
    raise NotImplementedError
