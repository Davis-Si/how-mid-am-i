# Stage 3 — Number Tools (handoff)

> **For the agent picking this up:** self-contained task spec. Read §1–3 for
> context, §4 for the work, §5 for verification. Builds directly on Stage 2's
> read layer (`src/howmid/data/queries.py`), which is implemented. **No LLM in
> this stage** — Invariant 1 stays live.

---

## 1. Project in one paragraph

"How Mid Am I?" — a conversational agent that takes a user's everyday
swim/bike/run PRs, projects them onto Ironman-equivalent performance, and
reports a real percentile vs. the historical Ironman field, with personality.
The load-bearing rule: **the number path is deterministic and the LLM never
touches it.** Full requirements in `how-mid-am-i-requirements.md`.

## 2. Current state (what Stage 3 builds on)

**Stage 2 is built and verified** — these are confirmed facts, not assumptions:

- **Warehouse:** `data/howmid.duckdb` has `fct_results` **built (886,768 rows)**:
  one row per (raceID, athleteID) finisher with columns `raceID, athleteID,
  year, cohort, gender, is_official, is_pro, overall_seconds, swim_seconds,
  bike_seconds, run_seconds` (segment seconds may be NULL — outliers NULLed
  upstream).
- **Read layer is DONE** — `src/howmid/data/queries.py` exposes, over a
  read-only connection (allowlist for the discipline→column identifier, bound
  params for cohort values):
  - `cohort_size(cohort, discipline) -> int` (counts non-null segment times)
  - `cohort_segment_seconds(cohort, discipline) -> list[int]` (ascending)
  - `cohort_median_seconds(cohort, discipline) -> float | None`
  - discipline ∈ {`swim`, `bike`, `run`, `overall`}, resolved via an allowlist;
    cohort is a canonical label like `'MPRO'`, `'M40-44'`.
- **THE SEAM GAP:** `queries.py` has size / median / full-list, but **no
  function that ranks a value against the cohort**. `percentile()` needs that.
  Stage 3 adds it — see §4B-bis. This is the one new addition to the data layer
  in this stage.
- **Config** (`src/howmid/config.py`): `IRONMAN_DISTANCES_M`
  (swim 3800, bike 180000, run 42195), `MIN_COHORT_SIZE` (=30),
  `OFFICIAL_AGE_BANDS`, `COHORT_GENDERS`. `RIEGEL_EXPONENT` / `FATIGUE_FACTOR`
  exist but are **DORMANT — do not use** (see §3).
- **Stubs to implement:** `src/howmid/tools/extrapolation.py` and
  `src/howmid/tools/percentile.py` (both currently raise `NotImplementedError`;
  dataclasses `Extrapolation` and `PercentileResult` are already defined there
  and re-exported via the facade — keep their shapes or extend, don't rename).

## 3. Conventions you must follow

- **Invariant 1 (LIVE):** nothing under `tools/`, `data/`, `guardrails/` may
  import `anthropic` or `howmid.llm`. `scripts/check_invariants.sh` must stay
  green. The number path is pure.
- **MODEL = linear scaling only.** Extrapolation is plain constant-pace
  scaling: `t2 = t1 * (D2 / D1)`. **NO Riegel power-law, NO fatigue factor** —
  the user deferred those. Do not reference `RIEGEL_EXPONENT` /
  `FATIGUE_FACTOR`.
- **No new SQL string-building from user input.** Reuse `queries.py`; if you
  add a query, follow its pattern (allowlist for identifiers, bound params for
  values).
- **Distances come from `config.IRONMAN_DISTANCES_M`**, never hard-coded.
- **UNITS CONTRACT — distance is metres, time is seconds.** Every distance that
  crosses into `tools/` is in **metres** (`IRONMAN_DISTANCES_M` is metres: swim
  3800, bike 180000, run 42195 — note run is the 42195 m marathon, NOT 42.195),
  and every time is in **integer/float seconds** (matching the warehouse's
  `*_seconds` columns). The extrapolation ratio `D2/D1` is unit-agnostic ONLY if
  both distances share a unit — so `extrapolate`'s `distance_m` argument MUST be
  metres. Converting the user's "5k" / "100km" / miles → metres is the **parse
  layer's** job (Stage 4), NOT this stage's. `extrapolate` trusts that
  `distance_m` is already metres; do not accept km here. (A km value reaching
  `extrapolate` as if metres is off by 1000× and silently wrong — the exact bug
  this contract prevents.)

## 4. The task

**Build order** (each step verifiable against the real DB before the next):
1. `extrapolate()` — pure math, no DB, independent. Test it first.
2. `cohort_rank()` in `queries.py` — the seam (§4B-bis). Sanity-check counts
   against a hand SQL query.
3. `percentile()` — composes `cohort_size` (refusal) + `cohort_rank` (§4C).
4. `eval/oracle.py` — the independent pandas check.
5. tests — extrapolation, then percentile-vs-oracle.

### 4A. Extrapolation (`tools/extrapolation.py`)
Implement `extrapolate(discipline, distance_m, seconds) -> Extrapolation`:
- Project the user's PR to the Ironman distance for that discipline by **linear
  distance scaling**:
  `ironman_seconds = seconds * (IRONMAN_DISTANCES_M[discipline] / distance_m)`.
  Both distances are **metres** (see §3 units contract); `distance_m` is assumed
  already converted from the user's km/miles by the parse layer.
- Return the existing `Extrapolation` dataclass with `is_estimate=True` (FR-5).
- Pure function, no I/O, no LLM.

### 4B. Comparison direction (DECIDED)
**Scale the user UP to the Ironman distance, then rank against the raw field.**
- The user gives a PR at some everyday distance; `extrapolate()` projects it to
  the Ironman split; `percentile()` ranks that projected time against
  `fct_results`' raw segment seconds for the cohort.
- Under linear scaling this yields the identical ranking to projecting the
  field down, with **no new dbt mart**. Do **not** build `field_pr_equivalent`.

### 4B-bis. The seam: add `cohort_rank()` to `queries.py` (the ONE data-layer addition)
`percentile()` needs to rank a value against a cohort, and `queries.py` has no
such function yet. Add one — **compute the rank in SQL** (FR-10: "percentile
computed in SQL, no LLM math"; also avoids pulling 100k+ rows into Python):

```python
def cohort_rank(cohort, discipline, value_seconds) -> tuple[int, int]:
    """Return (n_slower_or_equal_beaten, cohort_n) for value_seconds in cohort.
    Count-based rank computed in SQL over non-null segment times."""
```
- Follow the existing `queries.py` pattern exactly: discipline→column via the
  `_column_for` allowlist; `cohort` and `value_seconds` as **bound parameters**,
  never f-stringed in. Read-only connection.
- Return the raw counts (e.g. `COUNT(*) WHERE col < value` and the cohort total)
  and let `percentile()` turn them into a percentile — keeps the SQL dumb and the
  direction decision in one place.
- **"All finishers" default:** support `cohort=None` (or a sentinel) meaning *no
  cohort filter* — needed for the default whole-field comparison. Add it to
  `cohort_rank` (and, if convenient, the existing helpers) as a small read-only,
  parameterized branch. Document the choice.

### 4C. Percentile (`tools/percentile.py`)
Implement `percentile(discipline, value_seconds, cohort_filters) -> PercentileResult`:
- `value_seconds` is the **Ironman-distance** time (i.e. the output of
  `extrapolate`, or a raw Ironman split). The caller is responsible for having
  scaled to Ironman distance first; document this clearly.
- Resolve the cohort from `cohort_filters` (e.g. `{gender, age_group}` →
  canonical label like `M40-44`, or `MPRO`; `cohort_filters` empty/None → the
  all-finishers path from §4B-bis). Use the Stage 2 `queries.py` helpers +
  the new `cohort_rank`.
- **Refusal (FR-9):** call `cohort_size` first; if `< config.MIN_COHORT_SIZE`,
  return a `PercentileResult` with `sufficient=False`, `percentile=None`, the
  cohort size, and `cohort_median_seconds=None`. Do not compute a noisy
  percentile.
- **The percentile (FR-7, FR-10):** use `cohort_rank` (§4B-bis) — the rank is
  computed in SQL, percentile turns the counts into a number. **Direction:
  faster = better.** Document the convention — recommend "percentile = fraction
  of the field this athlete is FASTER than" (so 90 = top 10%). Add a test
  pinning the direction.
- **Out-of-range (DECIDED):** report the percentile **as it is mathematically**
  — a value faster than all finishers lands near the top (~99–100), slower than
  all lands near the bottom (~0). **Do NOT clamp or special-case.** Any
  "off-the-chart" messaging is a later concern (likely a conditional edge in the
  agent), not this tool's job.
- Framing (FR-11): the result represents rank "vs. Ironman finishers" — a fit,
  self-selected population. Encode this where it belongs (docstring / a field),
  not as LLM text.

### 4D. The eval oracle's first appearance (`eval/oracle.py`)
For testing the percentile **independently** (FR-21), implement a pandas-based
oracle that computes the same percentile straight from the DB with pandas —
NOT by calling `percentile()`. The percentile tests assert
`tool == oracle` within tolerance. This is the seed of the Stage-? eval harness;
keep it minimal here (just enough to verify the tool).

### 4E. Tests (`tests/`)
- `test_extrapolation.py` — hand-computed cases (e.g. 25:00 over 5000 m → run
  Ironman projection = 25:00 × 42195/5000; verify exact seconds). Include all
  three disciplines and a round-trip (scale up then down returns the original).
- `test_percentile.py`:
  - tool vs. pandas oracle on several known cohorts (e.g. `M40-44`, `MPRO`).
  - **refusal**: one of the 3 sub-`MIN_COHORT_SIZE` cells returns
    `sufficient=False`.
  - **direction**: a fast time ranks high, a slow time ranks low (pin it).
  - **out-of-range**: a time faster than the cohort min → percentile ≈ top, not
    clamped/errored; slower than max → ≈ bottom.

## 5. Definition of done
```bash
uv run pytest tests/                  # extrapolation + percentile (vs oracle) green
./scripts/check_invariants.sh         # Invariant 1 green (no LLM in tools/)
uv run ruff check src/ tests/ eval/   # lint clean
```
- `extrapolate()` and `percentile()` no longer raise `NotImplementedError`.
- `field_pr_equivalent` is NOT built. Riegel/fatigue remain unreferenced.
- From a cold `uv run python`: `from howmid import extrapolate, percentile`
  computes a grounded percentile for a sample PR end-to-end (no API key needed).

## 6. Out of scope (do not touch)
- Anything under `agent/`, `llm.py`, `app/`.
- `guardrails/grounding.py` (runtime answer-checking — needs the agent) and
  `guardrails/sql_guard.py` may be deferred unless `percentile()` adds raw SQL
  that should pass through the guard; if so, wire `sql_guard` in, else leave it.
- `guardrails/input_validation.py` — Stage 4 (the agent decides when to ask for
  clarification). `extrapolate`/`percentile` may assume already-valid inputs but
  should fail loudly (raise) on absurd values rather than return garbage.
- The full eval harness / report / version tracking — later stage. Only
  `eval/oracle.py` (enough to test) is in scope now.

## 7. Stage 4 preview (context, not your job)
Next is the **agent layer**: LangGraph state + nodes (parse → extrapolate →
compare → synthesize → critic) + the linear graph with conditional edges
(clarification, follow-ups reusing stored PRs, what-if, guardrail rejection),
and `llm.py` (the ONLY Anthropic import). The out-of-range "off-the-chart"
messaging the user mentioned lives there as a conditional edge — Stage 3 just
reports the honest number.
```
