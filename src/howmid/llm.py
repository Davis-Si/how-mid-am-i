"""The ONLY module permitted to import the Anthropic SDK.

INVARIANT 1 (greppable): every LLM call funnels through here. ``grep -rn
anthropic src/howmid/tools src/howmid/data src/howmid/guardrails`` must return
nothing — the number path cannot reach a model. The agent nodes import this
module for parsing (structured output) and persona; nothing else does.

Uses a cheap/fast model tier with a hard max_tokens cap (config.LLM_MODEL,
config.LLM_MAX_TOKENS) so the public demo cannot drain credits (NFR-2).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import anthropic


@lru_cache(maxsize=1)
def get_client() -> "anthropic.Anthropic":
    """Return a cached Anthropic client (reads ANTHROPIC_API_KEY from env)."""
    raise NotImplementedError
