"""Tests for the deterministic routers and the cohort-merge logic (no LLM).

These are the heart of "no LLM decides a path" — feed a state dict, assert the
chosen node name. Includes the missing-cohort→clarify case and the critic
retry/fallback cases the Stage 4 DoD requires.
"""

from __future__ import annotations

from howmid.agent.nodes import (
    MAX_SYNTH_ATTEMPTS,
    _merge_cohort,
    route_after_critic,
    route_after_parse,
)
from howmid.agent.prompts import CohortChange


class TestRouteAfterParse:
    def test_clarification_routes_to_ask(self):
        assert route_after_parse({"needs_clarification": True}) == "ask_clarification"

    def test_new_prs_routes_to_extrapolate(self):
        assert route_after_parse({"intent": "new_prs", "needs_clarification": False}) == "extrapolate"

    def test_follow_up_routes_to_extrapolate(self):
        assert route_after_parse({"intent": "follow_up", "needs_clarification": False}) == "extrapolate"


class TestRouteAfterCritic:
    def test_grounded_accepts(self):
        assert route_after_critic({"grounded": True, "synth_attempts": 1}) == "accept"

    def test_not_grounded_first_attempt_retries(self):
        # one attempt done (< MAX) → retry
        assert route_after_critic({"grounded": False, "synth_attempts": 1}) == "synthesize"

    def test_not_grounded_at_cap_falls_back(self):
        assert route_after_critic({"grounded": False, "synth_attempts": MAX_SYNTH_ATTEMPTS}) == "fallback"


class TestMergeCohort:
    def test_none_change_keeps_current(self):
        cohort, clar, _ = _merge_cohort({"gender": "M"}, None)
        assert cohort == {"gender": "M"} and clar is False

    def test_full_age_group_no_clarify(self):
        change = CohortChange(gender="M", age=42)
        cohort, clar, _ = _merge_cohort({}, change)
        assert cohort == {"gender": "M", "age_group": "40-44"} and clar is False

    def test_age_group_referenced_without_data_clarifies(self):
        # "now just my age group" with nothing on file → must ask
        change = CohortChange(age_group_referenced=True)
        cohort, clar, msg = _merge_cohort({}, change)
        assert clar is True and msg

    def test_age_group_referenced_with_stored_gender_still_needs_age(self):
        change = CohortChange(age_group_referenced=True)
        _, clar, msg = _merge_cohort({"gender": "M"}, change)
        assert clar is True and "age group" in msg

    def test_remembered_cohort_completes_on_followup(self):
        # gender known from before, now the age arrives → resolvable, no clarify
        change = CohortChange(age=42)
        cohort, clar, _ = _merge_cohort({"gender": "M"}, change)
        assert cohort == {"gender": "M", "age_group": "40-44"} and clar is False

    def test_pro_without_gender_clarifies(self):
        change = CohortChange(pro=True)
        _, clar, _ = _merge_cohort({}, change)
        assert clar is True

    def test_pro_with_gender_ok(self):
        change = CohortChange(pro=True, gender="F")
        cohort, clar, _ = _merge_cohort({}, change)
        assert cohort.get("pro") is True and clar is False
