"""Single source of truth for model constants and runtime settings.

INVARIANT 2 (greppable): the Riegel exponents and the fatigue factor live HERE
and nowhere else. Both call sites of the extrapolation model — the live Python
path (``tools/extrapolation.py``) and the precomputed dbt model
(``dbt/models/marts/field_pr_equivalent.sql``) — read these values rather than
hard-coding their own copy, so the two halves of the model can never drift.
The dbt model receives them as vars injected from this module.

These are the project's load-bearing assumptions (requirements sheet §12).
Every constant is named, defaulted, and citable — surfaced to the user as an
assumption, never hidden.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- Paths ------------------------------------------------------------------
# The built DuckDB warehouse (produced offline by scripts/clean_data.py +
# dbt). The app opens this READ-ONLY; see data/connection.py.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("HOWMID_DB", PROJECT_ROOT / "data" / "howmid.duckdb"))

# --- Ironman distances (metres) --------------------------------------------
IRONMAN_DISTANCES_M = {
    "swim": 3_800,
    "bike": 180_000,
    "run": 42_195,
}

# --- Riegel endurance exponents (T2 = T1 * (D2/D1)**k) ----------------------
# Running ~1.06 is the standard Riegel value. Swim/bike values are documented
# choices to be finalised during the model-building step (sheet §12, open
# decision). Placeholder-but-reasonable starting points; revisit with eval.
RIEGEL_EXPONENT = {
    "run": 1.06,
    "bike": 1.04,   # cycling fatigues less steeply with distance than running
    "swim": 1.03,   # swim scales closest to linear of the three
}

# --- Off-the-bike fatigue factor --------------------------------------------
# Ironman splits are raced fatigued, not fresh. The run (and optionally bike)
# projection is multiplied by this factor so the comparison reflects reality.
# Named constant with a source to cite; finalised during model-building (§12).
FATIGUE_FACTOR = {
    "run": 1.12,    # ~12% slower off the bike than an equivalent fresh run
    "bike": 1.00,   # not penalised by default; revisit
}

# --- Cohorts (official Ironman structure) -----------------------------------
# Ironman's official competition cohorts: PRO (M/F) and 5-year age-group bands
# by gender. The raw `division` field traces to these for 99.4% of clean
# finishers (see scripts/cohort_sizing.py). Single source of truth so the
# sizing script and the percentile engine agree on what a valid cohort is.
COHORT_GENDERS = ("M", "F")
OFFICIAL_AGE_BANDS = (
    "18-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54",
    "55-59", "60-64", "65-69", "70-74", "75-79", "80-84", "85-89",
)

# --- Percentile engine ------------------------------------------------------
# A cohort smaller than this returns a structured "insufficient data" signal
# instead of a noisy percentile (FR-9).
MIN_COHORT_SIZE = 30

# --- LLM --------------------------------------------------------------------
# Cheap/fast tier — the LLM only parses input and writes persona, never math
# (sheet NFR-2). Overridable via env for eval/version comparison.
LLM_MODEL = os.environ.get("HOWMID_MODEL", "claude-haiku-4-5")
LLM_MAX_TOKENS = int(os.environ.get("HOWMID_MAX_TOKENS", "1024"))
