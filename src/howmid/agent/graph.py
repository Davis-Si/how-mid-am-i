"""Wire the nodes into a LangGraph StateGraph with conditional edges.

Linear spine: parse -> (clarify? ) -> extrapolate -> compare -> synthesize ->
critic -> END, with conditional edges for clarification (FR-2), follow-ups
reusing stored PRs (FR-13), what-if deltas (FR-14), and guardrail rejection
(FR-17/18). A checkpointer provides multi-turn state.
"""

from __future__ import annotations


def build_graph(checkpointer=None):
    """Compile and return the HowMid agent graph."""
    raise NotImplementedError


def run_agent(message: str, thread_id: str = "default") -> str:
    """Public entry point: run one turn, return the guarded answer."""
    raise NotImplementedError
