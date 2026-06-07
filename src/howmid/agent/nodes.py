"""Graph nodes + deterministic routers.

A linear pipeline with conditional edges (NOT an LLM supervisor):

    parse → (clarify?) → extrapolate → compare → synthesize → critic
                                                      ↑ retry(≤1)   ↓
                                                  accept / fallback → answer

LLM touchpoints: parse_node, synthesize_node, critic_node (all via howmid.llm).
extrapolate/compare call the deterministic tools; the routers are pure Python
reading state fields the LLM filled. Unit conversion + number formatting are
deterministic (agent.units) — the LLM never computes a number.
"""

from __future__ import annotations

import json

from howmid import llm
from howmid.config import IRONMAN_DISTANCES_M
from howmid.agent.prompts import (
    CRITIC_SYSTEM,
    PARSE_SYSTEM,
    PERSONA_SYSTEM,
    CohortChange,
    CriticVerdict,
    ParseResult,
)
from howmid.agent.state import HowMidState
from howmid.agent.units import age_to_band, format_duration, metres_to_km, to_metres
from howmid.guardrails.input_validation import validate_pr
from howmid.tools.extrapolation import extrapolate
from howmid.tools.percentile import percentile

# Retries of the persona after a failed critic check (cap = 1 retry → 2 attempts).
MAX_SYNTH_ATTEMPTS = 2

# Race order is swim → bike → run. For each discipline: the Ironman leg label,
# and the legs the field had ALREADY completed before posting this split (so the
# persona can note the field's split came while fatigued). Built from config so
# the distances stay the single source of truth.
_KM = {d: f"{m / 1000:g} km" for d, m in IRONMAN_DISTANCES_M.items()}
_LEG_LABEL = {
    "swim": f"the {_KM['swim']} Ironman swim",
    "bike": f"the {_KM['bike']} Ironman bike",
    "run": f"the {_KM['run']} Ironman marathon",
}
_RACED_AFTER = {
    "swim": None,  # the swim is first — nothing before it
    "bike": f"a {_KM['swim']} swim",
    "run": f"a {_KM['swim']} swim and a {_KM['bike']} bike",
}


# ---------------------------------------------------------------------------
# Deterministic cohort merge (no LLM) — used by parse_node
# ---------------------------------------------------------------------------
def _merge_cohort(
    current: dict, change: CohortChange | None
) -> tuple[dict, bool, str | None]:
    """Merge a parsed cohort reference into the retained cohort.

    Returns (new_cohort, needs_clarification, clarification_message). Asks for
    clarification when the user references a narrower cohort ("my age group",
    "the pro field") but we lack the pieces to resolve it (FR-13 + missing-cohort
    rule). A cohort needs gender+age_group for an age group, or gender for pro.
    """
    cohort = dict(current)
    if change is None:
        return cohort, False, None

    if change.gender:
        cohort["gender"] = change.gender
    if change.age is not None:
        cohort["age_group"] = age_to_band(change.age)
    if change.pro:
        cohort["pro"] = True
        cohort.pop("age_group", None)  # pro is its own cohort, not an age band

    if cohort.get("pro"):
        if "gender" not in cohort:
            return cohort, True, "Sure — the men's or women's pro field?"
        return cohort, False, None

    if change.age_group_referenced or change.age is not None:
        missing = []
        if "gender" not in cohort:
            missing.append("gender")
        if "age_group" not in cohort:
            missing.append("age group")
        if missing:
            return cohort, True, f"Happy to — what's your {' and '.join(missing)}?"

    return cohort, False, None


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def parse_node(state: HowMidState) -> HowMidState:
    """LLM: one structured call → PRs (canonicalised to metres) + intent + cohort."""
    result: ParseResult = llm.parse_structured(
        PARSE_SYSTEM, state["user_message"], ParseResult
    )
    out: HowMidState = {"intent": result.intent}

    if result.intent == "unparseable" or result.needs_clarification:
        out["needs_clarification"] = True
        out["clarification"] = (
            result.clarification
            or "Tell me a personal best — e.g. 'I ran a 25-minute 5k'."
        )
        return out

    # New/what-if PRs: convert each to canonical metres (deterministic, not LLM).
    if result.prs:
        converted = [
            {
                "discipline": pr.discipline,
                "distance_m": to_metres(pr.value, pr.unit),
                "seconds": pr.seconds,
            }
            for pr in result.prs
        ]
        # Deterministic plausibility backstop (FR-2): reject impossible paces
        # before they reach the number path and produce a confident-wrong answer.
        for pr in converted:
            check = validate_pr(pr["discipline"], pr["distance_m"], pr["seconds"])
            if not check.ok:
                out["needs_clarification"] = True
                out["clarification"] = check.reason or "That PR doesn't look right — mind double-checking?"
                return out
        out["prs"] = converted

    # Merge cohort reference into retained cohort; may need clarification.
    cohort, needs_clar, clar = _merge_cohort(state.get("cohort", {}), result.cohort_change)
    out["cohort"] = cohort
    if needs_clar:
        out["needs_clarification"] = True
        out["clarification"] = clar
        return out

    # A follow-up with nothing stored and nothing new can't be compared.
    if not out.get("prs") and not state.get("prs"):
        out["needs_clarification"] = True
        out["clarification"] = "Give me a PR first — e.g. 'I ran a 25-minute 5k'."
        return out

    out["needs_clarification"] = False
    return out


def extrapolate_node(state: HowMidState) -> HowMidState:
    """Tools (no LLM): project each retained PR to its Ironman distance."""
    extraps = [
        extrapolate(pr["discipline"], pr["distance_m"], pr["seconds"])
        for pr in state.get("prs", [])
    ]
    return {"extrapolations": extraps}


def compare_node(state: HowMidState) -> HowMidState:
    """Tools (no LLM): rank each projection vs. the cohort. Resets the synth loop."""
    cohort = state.get("cohort", {})
    results = [
        percentile(ex.discipline, ex.ironman_seconds, cohort)
        for ex in state.get("extrapolations", [])
    ]
    return {"percentiles": results, "synth_attempts": 0, "critic_reason": ""}


def _build_payload(state: HowMidState) -> list[dict]:
    """Deterministic: the ONLY facts the persona/critic may use, pre-formatted.

    Times are formatted strings; distances echoed in km. Nothing here is computed
    by the LLM — the persona restates these, the critic checks against these.
    """
    extraps = {e.discipline: e for e in state.get("extrapolations", [])}
    payload = []
    for pr in state.get("percentiles", []):
        ex = extraps.get(pr.discipline)
        item: dict = {
            "discipline": pr.discipline,
            "cohort": pr.cohort_label or "all finishers",
            "population": pr.population,
            "is_estimate": True,
            # The field excludes the World Championship (Kona) — these are the
            # REGULAR Ironman circuit, i.e. not even the elite end of the sport.
            "excludes_world_championship": True,
            # The Ironman leg this projection is measured over, and the legs the
            # field had ALREADY raced before it (race order: swim→bike→run). Lets
            # the persona twist the knife — "...and that's after a 3.8 km swim."
            "ironman_leg": _LEG_LABEL[pr.discipline],
            "raced_after": _RACED_AFTER[pr.discipline],
        }
        if ex is not None:
            item["your_input"] = (
                f"{metres_to_km(ex.input_distance_m):g} km in {format_duration(ex.input_seconds)}"
            )
            item["projected_ironman_time"] = format_duration(ex.ironman_seconds)
        if pr.sufficient:
            pct = round(pr.percentile)
            item["percentile"] = pct
            # Meaner framing, same fact: how much of the field is FASTER than you.
            item["pct_of_field_faster_than_you"] = 100 - pct
            item["cohort_size"] = pr.cohort_size
            if pr.cohort_median_seconds is not None:
                item["cohort_median_time"] = format_duration(pr.cohort_median_seconds)
        else:
            item["insufficient_data"] = True
            item["cohort_size"] = pr.cohort_size
        payload.append(item)
    return payload


def synthesize_node(state: HowMidState) -> HowMidState:
    """LLM: persona delivery of the pre-computed payload (tone only, no new numbers)."""
    payload = _build_payload(state)
    user = json.dumps({"facts": payload}, indent=2)
    attempts = state.get("synth_attempts", 0)
    if attempts > 0 and state.get("critic_reason"):
        user += (
            f"\n\nYour previous draft was REJECTED for: {state['critic_reason']}\n"
            "Rewrite using ONLY the facts above; do not state any other number."
        )
    draft = llm.complete_text(PERSONA_SYSTEM, user)
    return {"draft": draft, "synth_attempts": attempts + 1}


def critic_node(state: HowMidState) -> HowMidState:
    """LLM judge: is every claim (numeric AND worded) in the draft supported?"""
    payload = _build_payload(state)
    user = (
        f"PAYLOAD (the only true facts):\n{json.dumps({'facts': payload}, indent=2)}\n\n"
        f"DRAFT to check:\n{state['draft']}"
    )
    verdict: CriticVerdict = llm.parse_structured(CRITIC_SYSTEM, user, CriticVerdict)
    return {"grounded": verdict.grounded, "critic_reason": verdict.reason}


def accept_node(state: HowMidState) -> HowMidState:
    """The critic passed the draft → it becomes the answer."""
    return {"answer": state["draft"]}


def fallback_node(state: HowMidState) -> HowMidState:
    """No LLM: a lightly-templated, friendly answer built straight from the numbers.

    Fires only when the persona failed the critic twice. Guaranteed grounded
    because Python assembles it from the payload — never ships a wrong number.
    """
    lines = ["Here's the straight read:"]
    for it in _build_payload(state):
        disc = it["discipline"]
        if it.get("insufficient_data"):
            lines.append(
                f"- {disc}: not enough finishers in {it['cohort']} "
                f"({it['cohort_size']}) to rank you fairly."
            )
            continue
        proj = it.get("projected_ironman_time", "?")
        pct = it.get("percentile")
        median = it.get("cohort_median_time")
        sentence = (
            f"- Your {it.get('your_input', disc)} projects to ~{proj} over the "
            f"Ironman {disc} — about {pct}th percentile vs {it['cohort']}"
        )
        sentence += f" (median {median})." if median else "."
        lines.append(sentence)
    lines.append("All projections are estimates, not measured times.")
    return {"answer": "\n".join(lines)}


def ask_clarification_node(state: HowMidState) -> HowMidState:
    """Surface the clarifying question as the answer (ends the turn)."""
    return {"answer": state.get("clarification") or "Could you rephrase that?"}


# ---------------------------------------------------------------------------
# Routers (pure Python — no LLM decides a path)
# ---------------------------------------------------------------------------
def route_after_parse(state: HowMidState) -> str:
    """Branch on the parse result. Returns the next node's name."""
    if state.get("needs_clarification"):
        return "ask_clarification"
    return "extrapolate"  # new_prs / follow_up / what_if all run the pipeline


def route_after_critic(state: HowMidState) -> str:
    """Accept if grounded; else retry the persona once; else fall back."""
    if state.get("grounded"):
        return "accept"
    if state.get("synth_attempts", 0) < MAX_SYNTH_ATTEMPTS:
        return "synthesize"
    return "fallback"
