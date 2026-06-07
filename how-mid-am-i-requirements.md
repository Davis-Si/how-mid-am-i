# "How Mid Am I?" — Requirements Sheet

**Project:** A conversational agent that takes a user's everyday personal bests (swim / bike / run) in plain chat, extrapolates them to an Ironman-equivalent, and tells them — with personality — exactly how mid they are relative to the field of real Ironman finishers.

**Context:** Weekend build. Portfolio artifact for the Legora Data & Analytics Intern application. Every requirement below exists to demonstrate one specific thing the role screens for: a *deployed agentic system* with tools, state, guardrails, an eval harness, and a deployment pipeline — not an LLM-wrapper script.

**One-line pitch:** "Tell it your 5k and your bike PR. It tells you how mid you are vs. people who race Ironmans."

**Example interaction:**
> User: "I can run 5k in 25 min and cycle 100km in 5 hours."
> Bot: "Respectable for a hobbyist. But projected onto an Ironman, ~90% of finishers go faster — and they do it *after* a 3.8k swim and 180k bike. Mid, but recoverable."

---

## 1. Goals & success criteria

The build is "done" when all of these are true:

- A stranger can open a public URL, type casual PRs ("ran 5k in 25, biked 100k in 5h"), and get a grounded, personality-driven percentile read in a few seconds.
- Every *percentile* the agent reports is computed from real data by a tool — it never invents a ranking.
- Every *extrapolated* figure is produced by a documented model and clearly framed as an estimate, never as a measured fact.
- It holds context across turns ("now just my age group", "what if I trained for a year").
- An eval harness scores it automatically and produces a report with real numbers.
- It survives being public: rate-limited, spend-capped, injection-resistant, read-only.

**Anti-goal (the failure mode to avoid):** an LLM that's handed times and asked to write a sassy roast with made-up percentiles. That is the exact "just called an API in a script" pattern the JD is tired of. Personality is a *delivery layer* on top of correct numbers; the extrapolation is a *transparent model*, never a vibe.

---

## 2. Scope

### In scope
- Casual PR input in any of the three disciplines, at arbitrary distances ("5k", "100km", "1500m swim").
- An extrapolation engine that maps everyday PRs to Ironman-equivalent performance using a documented endurance model + fatigue factor.
- Percentile comparison vs. the historical Ironman field, filterable by cohort (gender, age group where available).
- Multi-turn conversation with retained user PRs.
- Public demo on a neutral public dataset.
- Eval harness, guardrails, deployment.

### Out of scope (deliberately)
- **Multi-tenant accounts / per-user data upload.** Drags in auth, data isolation, persistence, per-user cost control — weeks of work, almost none on the JD. Public demo is single shared dataset, no login.
- Per-individual physiology (VO2max, training history). The model is population-level with documented assumptions, not a personalized coach.
- Exposing any personal data (PropLog, your own race/Strava history) on the public URL — separate private config only (stretch).
- Live scraping / real-time data. Use a static snapshot.
- Cosmetic polish beyond a usable, shareable chat UI.

---

## 3. Users

| Persona | Need | Noting |
|---|---|---|
| Casual athlete / runner | "Am I any good?" | Primary public user; has everyday PRs, not Ironman splits; wants a fast, funny, shareable answer |
| Interviewer (Legora) | Evaluate the engineering | Clicks the link, types numbers, then reads the repo/README |
| You (private mode) | Analyze your own training | Stretch goal; separate config, not public |

---

## 4. Functional requirements

### Input parsing
- **FR-1** Parse free-text PR statements into structured `(discipline, distance_m, time_seconds)` tuples across swim/bike/run. Handle varied phrasings ("5k in 25 min", "100km in 5 hours", "swim 1500m in 30"), multiple disciplines in one message, and missing disciplines.
- **FR-2** Validate parsed inputs: sane time/distance ratios (reject a 5-minute marathon or a 2-minute 100k), recognized units, plausible ranges. Ask a clarifying question when ambiguous rather than guessing.

### Extrapolation engine (new core component — the modeled layer)
- **FR-3** Within-discipline distance scaling via a documented endurance model (Riegel: `T2 = T1 × (D2/D1)^k`, with a per-discipline exponent `k`). Convert each user PR to the Ironman distance for that discipline (swim 3.8 km, bike 180 km, run 42.2 km).
- **FR-4** Apply a documented, configurable "off-the-bike" fatigue factor to the run (and optionally the bike) so the projection reflects that Ironman splits are raced fatigued, not fresh. The factor is a named constant with a cited source, surfaced as an assumption, not hidden.
- **FR-5** Every extrapolated value carries an `is_estimate=true` flag through to delivery. The agent must phrase these as projections ("you'd project to ~X"), never as facts ("you would finish in X").
- **FR-6** The model lives in one auditable place. Recommended direction: normalize the whole field *once* into everyday-PR-equivalent space (precompute), then compare the user's actual PR directly at query time.

### Percentile engine (deterministic — keeps ground truth)
- **FR-7** A deterministic tool `percentile(discipline, value, cohort_filters)` returning: percentile rank within the cohort, cohort size, and cohort median (plus the value at the 50th/90th percentile for context).
- **FR-8** Cohort filters: discipline, gender, age group (where the data supports it), defaulting to "all 140.6 finishers".
- **FR-9** Refuses (structured "insufficient data" signal) when the cohort is below a minimum size (e.g. 30) instead of returning a noisy percentile.
- **FR-10** Percentile computed in SQL (`PERCENT_RANK`/count-based) — no LLM math in the number path.
- **FR-11** Percentiles are explicitly framed as "vs. Ironman finishers" (a self-selected, fit population), never "vs. the general public".

### Agent (orchestration + state)
- **FR-12** LangGraph agent with nodes: parse PRs → extrapolate → plan comparisons → call percentile tool(s) → synthesize answer (persona).
- **FR-13** Conversation state retains the user's parsed PRs so follow-ups reuse them without re-entry ("now just my age group", "what about the pro field").
- **FR-14** Handles "what if" deltas by re-running the pipeline with modified inputs ("if I ran a 22-minute 5k").

### Conversation / persona layer
- **FR-15** Delivers grounded numbers in a consistent "humbling but playful" voice — deadpan, never cruel, always backed by the real stat. The uncertainty of estimates is absorbed into the humor, not concealed.
- **FR-16** Persona is confined to *delivery*; it cannot introduce numeric claims or override the estimate flag.

### Guardrails
- **FR-17** Grounding guard: any percentile in the response must trace to a tool call this turn; unsupported rankings are rejected before display.
- **FR-18** Estimate-honesty guard: extrapolated outputs are labeled as projections; the agent never asserts a measured finish time.
- **FR-19** Read-only enforcement at the DB layer (not just a prompt instruction); any generated SQL is validated `SELECT`-only, DDL/DML blocked.
- **FR-20** Prompt-injection resistance: user text is data, not instructions; persona and guardrails hold against "ignore your rules" inputs.

### Eval harness (the differentiator)
- **FR-21** A ground-truth set of 25–40 cases, scored automatically, in three layers:
  - *Percentile (deterministic, ground truth):* Ironman-equivalent value + cohort → expected percentile, where the expected value is computed independently (pandas oracle over the same data). Scored on absolute percentile error.
  - *Extrapolation (deterministic function):* PR input → expected Ironman-equivalent, hand-computed from the documented formula + fatigue constant. Scored on whether the agent applies the model correctly.
  - *Behavioral:* correct parsing of varied PR phrasings; correct cohort selection; correct refusal on small cohorts; correctly labels estimates as estimates.
- **FR-22** Runs as one command; emits a report: percentile MAE, extrapolation correctness, parse accuracy, refusal/honesty correctness, per-turn latency.
- **FR-23** Track metrics across at least two versions to show iteration (weaker → improved), not a single score.

### Deployment
- **FR-24** Public, clickable URL on a free tier. Recommended: Gradio on Hugging Face Spaces (fastest path to a public chat demo). Alternative for more engineering signal: FastAPI + minimal chat frontend, Dockerized.
- **FR-25** One-command local run (`docker run` or equivalent) for reproducibility.

---

## 5. Non-functional requirements

- **NFR-1 Latency:** target under ~5s per turn end-to-end.
- **NFR-2 Cost:** hard spend cap on LLM tokens; cheap/fast model tier; capped output tokens. The demo cannot drain credits.
- **NFR-3 Rate limiting:** per-IP limit on the public endpoint.
- **NFR-4 Reliability:** graceful failure — tool errors or unparseable input return a clear message, never a stack trace or a hallucinated answer.
- **NFR-5 Data safety:** public deploy uses only the neutral public dataset; no personal-data path reachable from the public URL.
- **NFR-6 Reproducibility:** pinned dependencies; dataset snapshot committed or scripted to download; the model's formula and constants version-controlled.

---

## 6. Data & model requirements

**Primary source:** Ironman 140.6 results, 2002–2024, three joinable CSVs (relational by ID).
**Optional splits source:** Ironman World Championship results with per-segment splits (swim / T1 / bike / T2 / run), for richer split-level percentiles.

**Target schema after dbt (adapt to the actual CSV columns):**

| Table | Key columns |
|---|---|
| `dim_race` | race_id, race_name, location, country, date, year, distance_type |
| `dim_athlete` | athlete_id, gender, age_group, country |
| `fct_results` | result_id, race_id, athlete_id, finish_status, overall_seconds, swim_seconds, t1_seconds, bike_seconds, t2_seconds, run_seconds, overall_rank, division_rank |

All times stored as integer seconds (parsed in staging). Percentiles computed over finishers only.

**Derived model table (precomputed):** `field_pr_equivalent` — each finisher's Ironman splits mapped *down* into everyday-PR-equivalent space (e.g. implied open-5k pace, implied 100k bike time) using the inverse of the extrapolation model, so the user's raw PR can be compared directly. This is where the documented formula + fatigue constant are applied, once, auditable.

---

## 7. Architecture (component flow)

```
User (NL: "ran 5k in 25 min, cycled 100k in 5h")
        │
        ▼
LangGraph agent ── retains state (parsed PRs) across turns
  parse PRs → extrapolate (model) → call percentile tool → synthesize (persona)
        │                                   ▲
        ▼                                   │ grounded percentile only
Extrapolation engine (Riegel + fatigue) ──► Percentile tool ──► DuckDB (dbt: fct_results,
   estimates flagged is_estimate                                  field_pr_equivalent)
        │
        ▼
Guardrails: grounding · estimate-honesty · input validation · read-only · injection
        │
        ▼
Public chat UI (Gradio / HF Spaces)  +  rate limit + spend cap

Offline:  Eval harness ──► percentile / extrapolation / behavioral cases ──► metrics report
```

---

## 8. Tech stack

- **Orchestration:** LangGraph (state + tool routing)
- **Data:** DuckDB + dbt-duckdb
- **Model:** documented endurance formula (Riegel) + fatigue constant, in version-controlled code
- **Oracle for eval:** pandas (independent percentile + formula computation)
- **Backend:** Python; FastAPI *or* Gradio
- **Deploy:** Hugging Face Spaces (Gradio) or Docker + Render/Fly/Railway (FastAPI)
- **LLM:** a cheap/fast hosted tier (cost-capped), used only for parsing + persona, never for math

---

## 9. Two-day build plan

### Day 1 — data + model + engine + agent core
1. Load the three CSVs into DuckDB.
2. dbt staging (parse times → seconds) + `fct_results` mart.
3. Implement + unit-test the extrapolation model (Riegel + fatigue) against hand-computed values; build `field_pr_equivalent`.
4. Build + unit-test the `percentile` tool against the pandas oracle.
5. LangGraph agent working end-to-end in a script: casual PR in → grounded, estimate-flagged percentile out.

### Day 2 — production-ify + ship
6. Multi-turn state + follow-ups (FR-13, FR-14).
7. Guardrails: grounding, estimate-honesty, validation, read-only (FR-17–20).
8. Eval harness + run + report; do one improvement pass and record before/after (FR-21–23).
9. Persona layer (FR-15–16) — keep to ~20% of remaining time.
10. Deploy to public URL with rate limit + spend cap (FR-24, NFR-2/3).
11. README with the architecture diagram and the eval results table.

**Discipline:** ~80% on data + model + agent + eval + guardrails + deploy; ~20% on persona. The roast writes itself once the percentile and extrapolation engines are correct — those are the parts that earn the interview.

---

## 10. Stretch goals (only if core is shipped)
- Private config pointed at your own training/race data, decoupled from the public build.
- Explicit "what if I trained for a year" simulator in the UI.
- One-tap comparison against the pro field.
- Shareable result card (image/text) — amplifies the viral hook.
- Add 70.3 as a second distance.
- Age-graded comparison using published age-grade tables.

---

## 11. What each requirement proves (interview mapping)

| JD expectation | Requirement(s) that demonstrate it |
|---|---|
| Built & deployed an agentic system | FR-12, FR-24, FR-25 |
| Agent with tools and state | FR-7, FR-12, FR-13 |
| Integrates with a data stack | FR-1..FR-10 (DuckDB + dbt) |
| Modeling judgment on noisy input | FR-3, FR-4, FR-6, FR-21 (extrapolation layer) |
| Evaluation harness | FR-21–23 |
| Observability / reliability / guardrails | FR-17–20, NFR-4 |
| Bias to shipping; still used after you leave | Public URL + the shareable hook |
| Thinks like an engineer, not a prototyper | Read-only DB, spend cap, injection resistance, estimate-honesty, refusal logic |

---

## 12. Open decisions to confirm before starting
- Endurance exponents: which Riegel exponent per discipline? (Running ~1.06 is standard; pick + document cycling/swim values.)
- Fatigue factor: which published source/value for the off-the-bike run penalty, and is it applied to the bike too? (Document it; surface as an assumption.)
- Normalization direction: field → PR-equivalent (recommended) vs. user PR → Ironman-equivalent. (Recommend field-side, precomputed.)
- Cohort granularity: does the dataset carry age group reliably, or only gender? (Verify on load — determines how specific comparisons can get.)
- Hosting: Gradio/HF Spaces for speed vs. FastAPI+Docker for engineering signal. (Pick by how much time §9 leaves.)
- Persona tone ceiling: how humbling is too humbling? (Deadpan, data-backed, never personal.)
