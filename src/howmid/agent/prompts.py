"""Versioned prompts: structured-output parsing schema-prompt + persona.

Kept here so prompt changes are version-controlled and the eval harness can
track behaviour across at least two prompt/model versions (FR-23). The persona
is a DELIVERY layer only — it may never introduce a numeric claim or override
the is_estimate flag (FR-16).
"""

from __future__ import annotations

PARSE_SYSTEM = "TODO: instruct structured extraction of (discipline, distance_m, seconds)."
PERSONA_SYSTEM = "TODO: humbling-but-playful delivery, grounded in supplied numbers only."
