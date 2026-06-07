"""Gradio chat UI for "How Mid Am I?" — a thin adapter over howmid.run_agent.

All intelligence lives behind run_agent(message, thread_id). This layer only:
  * renders the chat,
  * maps each browser session to a stable thread_id (so multi-turn memory works
    per user and stays isolated between users),
  * throttles per session (NFR-3, demo-grade),
  * surfaces errors as friendly text, never a stack trace (NFR-4).

It imports `howmid` for run_agent and nothing from the number path or the LLM
SDK (Invariant 1 holds at the app layer too).
"""

from __future__ import annotations

import time
import uuid
from collections import deque

import gradio as gr

from howmid import run_agent

# --- per-session throttle (in-process; fine for a single-replica demo) ------
_MAX_PER_WINDOW = 10          # messages...
_WINDOW_SECONDS = 60          # ...per rolling 60s, per session
_hits: dict[str, deque[float]] = {}


def _throttled(session_id: str) -> bool:
    """True if this session has exceeded the rate limit (and records the hit)."""
    now = time.monotonic()
    q = _hits.setdefault(session_id, deque())
    while q and now - q[0] > _WINDOW_SECONDS:
        q.popleft()
    if len(q) >= _MAX_PER_WINDOW:
        return True
    q.append(now)
    return False


def respond(message: str, history: list, session_id: str) -> str:
    """ChatInterface callback: throttle → run_agent → string."""
    if not message or not message.strip():
        return "Tell me a personal best — e.g. 'I ran a 25-minute 5k'."
    if _throttled(session_id):
        return "You're going fast — give me a few seconds and try again. 🙂"
    try:
        answer = run_agent(message, thread_id=session_id)
    except Exception:
        # NFR-4: never leak a stack trace to the user.
        return (
            "Something went wrong on my end crunching that — try rephrasing your "
            "PR, e.g. 'I swam 1500m in 30 min'."
        )
    return answer or "I didn't catch a PR in that — try 'I biked 100k in 5 hours'."


INTRO = "# How Mid Am I? 🏊🚴🏃"

# The agent's opening line in the chat window — a single question that sets
# context and asks for the three PRs.
GREETING = (
    "Hi — I rank you against people who've actually finished an Ironman. "
    "What are your PRs for running, cycling, and swimming? "
    "(distance + time for each, e.g. \"10k in 48 min\")"
)

DISCLAIMER = (
    "*Every percentile is real, computed from 886,768 Ironman finishers "
    "(2002–2024). Every projected time is an estimate, not a measured result.*"
)

EXAMPLES = [
    "My longest run is a half marathon in 1:55",
    "I ran 10k in 48 min, biked 100k in 5h, and swam 1500m in 32 min",
    "Best bike: 40k in 1h20",
]


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="How Mid Am I?", fill_height=True) as demo:
        gr.Markdown(INTRO)
        # Per-browser-session thread_id: created once per session, isolates users.
        session_id = gr.State(lambda: uuid.uuid4().hex)

        # Seed the chat with the agent's opening question so the user gets
        # context up front, conversationally, rather than a wall of intro text.
        chatbot = gr.Chatbot(
            value=[{"role": "assistant", "content": GREETING}],
            height=420,
        )
        gr.ChatInterface(
            fn=respond,
            chatbot=chatbot,
            additional_inputs=[session_id],
            examples=[[e] for e in EXAMPLES],
        )

        gr.Markdown(DISCLAIMER)

        def _reset() -> str:
            # rotate the session id → a fresh conversation (clears retained PRs)
            return uuid.uuid4().hex

        gr.Button("Start over", variant="secondary").click(
            _reset, outputs=session_id
        )
    return demo


demo = build_demo()


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
