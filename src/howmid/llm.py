"""The ONLY module permitted to import the Anthropic SDK.

INVARIANT 1 (greppable): every LLM call funnels through here. ``grep -rn
anthropic src/howmid/tools src/howmid/data src/howmid/guardrails`` must return
nothing — the number path cannot reach a model. The agent nodes import this
module for parsing (structured output), persona, and the critic; nothing else
does.

Uses a cheap/fast model tier with a hard max_tokens cap (config.LLM_MODEL,
config.LLM_MAX_TOKENS) so the public demo cannot drain credits (NFR-2). The LLM
here only reads/labels (parse), writes prose (persona), and judges grounding
(critic) — it never computes a number.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, TypeVar

from howmid import config

if TYPE_CHECKING:
    import anthropic
    from pydantic import BaseModel

    T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=1)
def get_client() -> "anthropic.Anthropic":
    """Return a cached Anthropic client (reads ANTHROPIC_API_KEY from env)."""
    import anthropic

    return anthropic.Anthropic()


def parse_structured(
    system: str,
    user_message: str,
    schema: "type[T]",
    *,
    max_tokens: int | None = None,
) -> "T":
    """One structured-output call: returns a validated instance of ``schema``.

    Used for the parse node and the critic (both want schema-validated JSON, not
    free text). The SDK validates the response against the Pydantic model and
    raises on mismatch, so callers get a typed object or an error — never
    half-parsed text.
    """
    client = get_client()
    response = client.messages.parse(
        model=config.LLM_MODEL,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        output_format=schema,
    )
    return response.parsed_output


def complete_text(
    system: str,
    user_message: str,
    *,
    max_tokens: int | None = None,
) -> str:
    """A plain text completion: returns the concatenated text blocks.

    Used for the persona (synthesize) node, which produces prose, not JSON.
    """
    client = get_client()
    response = client.messages.create(
        model=config.LLM_MODEL,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return "".join(block.text for block in response.content if block.type == "text")
