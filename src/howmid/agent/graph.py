"""Wire the nodes into a LangGraph StateGraph with conditional edges.

Topology (Stage 4 §4A):

    START → parse → ◇route_after_parse ─┬─ ask_clarification → END
                                        └─ extrapolate → compare → synthesize
                                           → critic → ◇route_after_critic ─┬─ accept → END
                                                                           ├─ synthesize (retry ≤1)
                                                                           └─ fallback → END

A checkpointer (MemorySaver for the demo) persists `prs` and `cohort` across
turns, keyed by thread_id (FR-13/14). Swapping to the SQLite checkpointer
(langgraph-checkpoint-sqlite, already installed) is a one-line change.
"""

from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from howmid.agent import nodes
from howmid.agent.state import HowMidState


def build_graph(checkpointer=None):
    """Build and compile the HowMid agent graph."""
    g = StateGraph(HowMidState)

    g.add_node("parse", nodes.parse_node)
    g.add_node("extrapolate", nodes.extrapolate_node)
    g.add_node("compare", nodes.compare_node)
    g.add_node("synthesize", nodes.synthesize_node)
    g.add_node("critic", nodes.critic_node)
    g.add_node("accept", nodes.accept_node)
    g.add_node("fallback", nodes.fallback_node)
    g.add_node("ask_clarification", nodes.ask_clarification_node)

    g.add_edge(START, "parse")
    g.add_conditional_edges(
        "parse", nodes.route_after_parse, ["extrapolate", "ask_clarification"]
    )
    g.add_edge("extrapolate", "compare")
    g.add_edge("compare", "synthesize")
    g.add_edge("synthesize", "critic")
    g.add_conditional_edges(
        "critic", nodes.route_after_critic, ["accept", "synthesize", "fallback"]
    )
    g.add_edge("accept", END)
    g.add_edge("fallback", END)
    g.add_edge("ask_clarification", END)

    return g.compile(checkpointer=checkpointer or MemorySaver())


@lru_cache(maxsize=1)
def _default_graph():
    """Process-wide compiled graph with an in-memory checkpointer."""
    return build_graph()


def run_agent(message: str, thread_id: str = "default") -> str:
    """Public entry point: run one turn on ``thread_id``, return the answer.

    State (PRs, cohort) persists across calls with the same thread_id via the
    checkpointer — this is what makes follow-ups ("now just my age group") work.
    """
    graph = _default_graph()
    result = graph.invoke(
        {"user_message": message},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result.get("answer", "")
