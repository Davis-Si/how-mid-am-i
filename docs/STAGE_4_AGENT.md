# Stage 4 — LangGraph Agent (handoff)

> **For the agent picking this up:** self-contained task spec. Read §1–3 for
> context, §4 for the design (all decisions are made — don't re-litigate), §5
> for the work, §6 for verification. Stages 1–3 are done: the deterministic
> number path works end-to-end. This stage adds the LLM + orchestration on top.
> This is the FIRST stage that touches the Anthropic SDK — only via `llm.py`.

---

## 1. Project in one paragraph

"How Mid Am I?" — a conversational agent that takes a user's everyday
swim/bike/run PRs, projects them onto Ironman-equivalent performance, and
reports a real percentile vs. the historical Ironman field, with personality.
The load-bearing rule: **the number path is deterministic and the LLM never
computes a number.** Full requirements in `how-mid-am-i-requirements.md`.

## 2. Current state (what Stage 4 builds on)

**Stages 1–3 done and verified.** Confirmed facts:

- **Tools (Stage 3, working):**
  - `howmid.extrapolate(discipline, distance_m, seconds) -> Extrapolation`
    — linear scaling `t * (D_ironman/D_user)`; `distance_m` in **metres**;
    `is_estimate=True`. Raises `ValueError` on bad input.
  - `howmid.percentile(discipline, value_seconds, cohort_filters) -> PercentileResult`
    — `value_seconds` is an **Ironman-distance** time; ranks vs the field;
    refuses (`sufficient=False`, `percentile=None`) below `MIN_COHORT_SIZE`;
    faster = higher percentile (0–100); `cohort_filters` is `{gender, age_group,
    pro}` (gender 'M'/'F'/'Male'/'Female'; age_group '40-44' or 'M40-44'; pro
    bool) or empty/`{}` → all-finishers. Already resolves cohort labels and
    stamps `population`.
- **Data layer:** read-only, `fct_results` (886,768 finishers). The tools own
  all DB access; the agent calls the tools, never the DB.
- **Config** (`src/howmid/config.py`): `IRONMAN_DISTANCES_M` (metres),
  `OFFICIAL_AGE_BANDS`, `COHORT_GENDERS`, `MIN_COHORT_SIZE` (=30),
  `LLM_MODEL` (`claude-haiku-4-5`), `LLM_MAX_TOKENS` (=1024).
- **Stubs to implement (all raise `NotImplementedError` / are TODO):**
  - `src/howmid/llm.py` — `get_client()` (the ONLY Anthropic import).
  - `src/howmid/agent/state.py` — `HowMidState` (TypedDict; extend as needed).
  - `src/howmid/agent/prompts.py` — `PARSE_SYSTEM`, `PERSONA_SYSTEM` (+ a critic
    prompt you'll add).
  - `src/howmid/agent/nodes.py` — `parse_node`, `extrapolate_node`,
    `compare_node`, `synthesize_node`, `critic_node` (+ `ask_clarification`,
    `fallback` nodes you'll add).
  - `src/howmid/agent/graph.py` — `build_graph(checkpointer)`, `run_agent(message,
    thread_id)`.
  - `src/howmid/guardrails/input_validation.py` — `validate_pr(...)` (used by
    the parse/extrapolate path; FR-2).
  - **Note:** `guardrails/grounding.py` exists with regex-style stubs
    (`check_grounded`, `check_estimate_honesty`). The critic is an **LLM judge**
    (see §4G) — you may leave those stubs unused or repurpose; don't be misled by
    them.

## 3. Conventions you must follow

- **Invariant 1 (LIVE, critical this stage):** the LLM lives ONLY in `llm.py`
  and is called ONLY from `agent/nodes.py` (parse, synthesize, critic). Nothing
  under `tools/`, `data/`, `guardrails/` may import `anthropic` or `howmid.llm`.
  `scripts/check_invariants.sh` must stay green.
- **The LLM never computes a number.** It parses (reads/labels), writes persona
  prose, and judges grounding. Every number comes from the tools. Unit
  conversion and time formatting are **deterministic Python**, not the LLM.
- **Units contract:** metres + seconds internally. The parse LLM emits
  `{value, unit}`; deterministic Python converts to metres before `extrapolate`.
  Output formatting (seconds→`h:mm:ss`, metres→km) is deterministic, done before
  the persona LLM sees the numbers. See §4C.
- **Cheap tier + capped tokens:** all LLM calls use `config.LLM_MODEL` with
  `max_tokens=config.LLM_MAX_TOKENS` (NFR-2). Set in `llm.py` / per call.
- **Structured outputs** for parse and critic (Pydantic + `messages.parse` or
  `output_config.format`) so the model's JSON is schema-validated.

## 4. The design (DECIDED — build to this, don't redesign)

### 4A. Topology — linear graph + conditional edges (NO supervisor)
```
START → parse → ◇route_after_parse
                   ├─ needs_clarification ─→ ask_clarification → END
                   ├─ follow_up/what_if/new_prs ─→ extrapolate
                   └─ (cohort referenced but unknown) ─→ ask_clarification → END
        extrapolate → compare → synthesize → critic → ◇route_after_critic
                                                          ├─ grounded ─→ END
                                                          ├─ !grounded & attempts<1 ─→ synthesize (retry)
                                                          └─ else ─→ fallback → END
```
Routing is **deterministic Python** reading `state` fields the LLM filled. No
LLM decides a path. (See `docs/` discussion — this is the settled "no
supervisor" stance.)

### 4B. Parse — ONE structured LLM call does parse + intent (DECIDED)
`parse_node` makes a single structured call returning:
```python
class ParseResult(BaseModel):
    intent: Literal["new_prs", "follow_up", "what_if", "unparseable"]
    prs: list[PRInput]          # PRInput: {discipline, value: float, unit: "km"|"m"|"mi"|"yd", seconds: int}
    cohort_change: CohortChange | None   # {gender?, age?, age_group?, pro?}
    needs_clarification: bool
    clarification: str | None    # the question to ask, if any
```
- The LLM **labels** units, it does **not** convert (no `distance_m` from the
  LLM). It may emit raw `age` (e.g. 42); Python bands it to `40-44`.
- Intent is data the LLM extracted; the **deterministic** `route_after_parse`
  branches on it.

### 4C. Units & formatting — deterministic, at the boundaries (DECIDED)
- **Input:** a pure `to_metres(value, unit)` helper converts km/mi/yd/m →
  metres. Add an `age_to_band(age)` helper (e.g. 42 → '40-44') using
  `config.OFFICIAL_AGE_BANDS`. Both unit-tested, no LLM.
- **Output:** a `format` helper builds the persona payload: seconds →
  `h:mm:ss` / `m:ss`, metres → km for any echoed distance. The persona LLM
  receives **pre-formatted strings**, never raw seconds.

### 4D. Comparison flow (uses Stage 3 tools)
- `extrapolate_node`: for each PR in state, `to_metres` → `extrapolate(...)` →
  store `Extrapolation` list. (km→m happens here or in parse; do it once,
  document where.)
- `compare_node`: for each extrapolation, `percentile(discipline,
  ironman_seconds, cohort_filters)` where `cohort_filters` comes from state
  (persisted cohort). Store `PercentileResult` list.

### 4E. Cohort capture & memory (DECIDED)
- Cohort lives in `state` and **persists across turns** (via checkpointer).
- Captured by the parse call's `cohort_change` whenever the user mentions
  age/gender ("I'm a 42M", "the pro field"). No upfront interrogation.
- **Default = all-finishers** when unknown (Stage 3 already defaults there).
- **Missing-but-referenced → clarify:** if the user references a cohort
  ("now just my age group") but state lacks gender+age, `route_after_parse`
  routes to `ask_clarification` ("What's your age group and gender?"). Next turn
  supplies it and re-runs. Detection is a deterministic check in the router:
  *cohort referenced AND (gender or age missing) → clarify.*

### 4F. State persistence (DECIDED)
- **In-memory `MemorySaver`**, keyed by `thread_id`. Lost on restart — fine for
  the demo (no per-user accounts in scope). Swapping to the SQLite checkpointer
  (`langgraph-checkpoint-sqlite`, already installed) is a one-line change; note
  this in a comment.

### 4G. Persona + critic (DECIDED — this is the heart of FR-15–18)
- **synthesize_node:** receives a **structured, pre-formatted numbers payload**
  (context-rich but minimal: projected time(s), percentile(s), cohort label +
  size, input echo, `is_estimate`). System prompt = humbling-but-playful
  delivery; persona is **tone only**. Persona is FREE to phrase qualitatively
  ("top third", "most of the field") — latitude is allowed (1-c).
- **critic_node = a SECOND LLM call (LLM judge).** It judges grounding FULLY:
  *is every claim in the draft — numeric AND worded — supported by the payload?*
  Structured output: `{grounded: bool, reason: str}`. This is what makes the
  persona's latitude safe: free phrasing is fine *as long as the judge finds it
  supported*. A fabricated "you'd crush 80%" or an estimate stated as fact →
  `grounded=false`.
- **Failure handling (DECIDED): retry once (cap=1), then fallback.**
  `route_after_critic`: grounded → END; not grounded & `synth_attempts < 1` →
  back to `synthesize` (pass the judge's `reason` as corrective feedback,
  increment `synth_attempts`); else → `fallback`.
- **fallback_node:** emits a **lightly-templated, friendly** answer built
  directly from the numbers payload in Python (no LLM) — guaranteed grounded.
  Fires only when the persona failed twice. Tone: friendly but plain, e.g.
  "Here's the straight read: your run projects to ~4:32 — that's 68th percentile
  among M40-44 finishers (median 4:51). Take it as an estimate."

### 4H. LLM call budget (consequence, for latency awareness — NFR-1)
Common path = **3 calls/turn** (parse, synthesize, critic). +1 on retry. All on
the cheap tier, `max_tokens` capped. Clarification turns = 1 call (parse only).

## 5. The work (build order)

1. **`llm.py`** — `get_client()` returns a cached `anthropic.Anthropic()`. Add a
   thin helper for a structured call (model + `max_tokens` from config) so
   nodes don't repeat boilerplate.
2. **Deterministic helpers** — `to_metres`, `age_to_band`, and the output
   `format` helpers (new small module, e.g. `agent/units.py` or under tools;
   keep LLM-free). Unit-test first.
3. **`prompts.py`** — `PARSE_SYSTEM`, `PERSONA_SYSTEM`, `CRITIC_SYSTEM`, and the
   Pydantic schemas (`ParseResult`, `PersonaPayload`, `CriticVerdict`).
4. **`state.py`** — extend `HowMidState` with `intent`, `cohort` (persisted),
   `synth_attempts`, `grounded`, `critic_reason` as needed.
5. **`nodes.py`** — the 7 nodes (parse, extrapolate, compare, synthesize,
   critic, ask_clarification, fallback) + the two routing functions.
6. **`graph.py`** — `build_graph(MemorySaver())` wiring §4A; `run_agent(message,
   thread_id)` invokes with `config={"configurable": {"thread_id": thread_id}}`
   and returns the final `answer`.
7. **Tests** (see §6).

## 6. Definition of done

```bash
uv run pytest tests/                  # incl. new agent tests
./scripts/check_invariants.sh         # Invariant 1 green (LLM only in llm.py/agent)
uv run ruff check src/ tests/
```
- **`grep -rn anthropic src/howmid/tools src/howmid/data src/howmid/guardrails`
  returns nothing.**
- Deterministic helpers (`to_metres`, `age_to_band`, formatters) are unit-tested
  WITHOUT the LLM — these are pure functions and must be rock-solid.
- Routing functions are unit-tested WITHOUT the LLM (feed a state dict, assert
  the returned node name) — incl. the missing-cohort→clarify case and the
  critic retry/fallback cases.
- **Live smoke test (needs `ANTHROPIC_API_KEY`):** `run_agent("I ran a 25 min
  5k", "t1")` returns a grounded persona answer; a follow-up `run_agent("now
  just my age group", "t1")` on the same thread asks for age/gender (cohort
  memory + clarify path). Gate LLM-dependent tests behind a key check so the
  suite passes offline.
- Mock the LLM where possible so node logic is tested without burning tokens;
  keep one optional live smoke test.

## 7. Out of scope (do not touch)
- The app/UI (`app/chat.py`), per-IP rate limit, aggregate spend counter —
  Stage 5. Only the per-call `max_tokens` cap is in scope here.
- The full eval harness / version tracking — later stage. (The critic-vs-no-
  critic split is a natural v1→v2 eval story, but not your job now.)
- `scripts/clean_data.py`, `cohort_sizing.py`, dbt models, Stage 3 tools — done,
  leave them.
- `RIEGEL_EXPONENT` / `FATIGUE_FACTOR` — still dormant; linear scaling only.

## 8. Stage 5 preview (context, not your job)
Gradio chat UI + deploy (HF Spaces) + per-IP rate limit + aggregate spend
counter + README architecture/eval section. `run_agent(message, thread_id)` is
the seam the UI calls; keep its signature clean.
