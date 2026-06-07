"""How Mid Am I? — grounded Ironman-percentile conversational agent.

Curated public API (facade): consumers import the handful of callables they
actually use straight from ``howmid``; the deep module layout underneath can be
refactored freely without breaking them.

    from howmid import extrapolate, percentile, run_agent
"""

from __future__ import annotations

from howmid.tools.extrapolation import Extrapolation, extrapolate
from howmid.tools.percentile import PercentileResult, percentile
from howmid.agent.graph import run_agent

__all__ = [
    "extrapolate",
    "Extrapolation",
    "percentile",
    "PercentileResult",
    "run_agent",
]

__version__ = "0.1.0"
