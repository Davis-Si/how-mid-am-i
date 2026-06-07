# Stage 2 — Data Layer (handoff)

> **For the agent picking this up:** this is a self-contained task spec. Read
> §1–3 for context, §4 for the work, §5 for how to verify. The backbone
> (Stage 1) is done and verified; you are building on top of it. Do **not**
> re-run `scripts/clean_data.py` — the warehouse already exists and verifies.

---

## 1. Project in one paragraph

"How Mid Am I?" — a conversational agent that takes a user's everyday
swim/bike/run PRs, projects them onto Ironman-equivalent performance, and
reports a real percentile vs. the historical Ironman field, with personality.
The load-bearing rule: **the number path is deterministic and the LLM never
touches it.** Full requirements in `how-mid-am-i-requirements.md`.

## 2. Current state (what exists)

- **Tooling:** uv + hatchling, src layout, `uv.lock` committed. Run everything
  via `uv run …`. Python 3.12.
- **Package:** `src/howmid/` — most modules are documented **stubs that raise
  `NotImplementedError`**. Facade in `src/howmid/__init__.py`. **Implemented in
  this stage:** `data/connection.py` (`read_only_connection()`) and
  `data/queries.py` (`cohort_size`, `cohort_segment_seconds`,
  `cohort_median_seconds`). The `tools/`, `guardrails/`, `agent/`, `llm.py`
  modules remain stubs.
- **Config:** `src/howmid/config.py` is the single source of truth for
  constants. Already defines: `DB_PATH`, `IRONMAN_DISTANCES_M`,
  `OFFICIAL_AGE_BANDS`, `COHORT_GENDERS`, `MIN_COHORT_SIZE` (=30), `LLM_MODEL`.
  It also defines `RIEGEL_EXPONENT` and `FATIGUE_FACTOR` — **these are DORMANT,
  do not use them** (see §3 model note).
- **Warehouse:** `data/howmid.duckdb` (gitignored, ~190MB) already contains a
  clean `clean_results` table — **886,768 finishers**, built by
  `scripts/clean_data.py`. Schema below (§4A).
- **Cohort facts:** `scripts/cohort_sizing.py` → `data/cohort_sizing.json`.
  99.42% of finishers map to official cohorts; **23/26** age×gender cells clear
  `MIN_COHORT_SIZE`. PRO sizes: MPRO=8678, FPRO=4886. Use these numbers as test
  assertions.
- **dbt:** project skeleton at `dbt/` (`dbt_project.yml`, `profiles.yml` → 
  `../data/howmid.duckdb`). `uv run dbt debug` passes. **No models yet** — empty
  `models/staging/` and `models/marts/`.

## 3. Conventions you must follow

- **Invariant 1 (LIVE):** nothing under `src/howmid/tools/`, `data/`,
  `guardrails/` may import `anthropic` or `howmid.llm`. Enforced by
  `scripts/check_invariants.sh` — it must stay green.
- **Invariant 2 (DORMANT this stage):** model constants live only in
  `config.py`. No Riegel/fatigue constants are in play this stage, so this is
  effectively idle — but don't hard-code physical distances either; read them
  from `config.IRONMAN_DISTANCES_M` / `config.OFFICIAL_AGE_BANDS`.
- **Single source of cohort truth:** the cohort-mapping logic already exists in
  `scripts/cohort_sizing.py` (`cohort_case_sql()`), driven by
  `config.OFFICIAL_AGE_BANDS` + `COHORT_GENDERS`. The dbt `stg_results` model
  must reproduce *exactly that* logic, with bands injected as a dbt var sourced
  from config — do not fork a second definition.
- **Read-only everywhere in the app path:** the package never opens the
  warehouse writable. dbt is the only writer, and only offline.
- **MODEL NOTE — keep it simple:** extrapolation (Stage 3) will be **plain
  linear distance scaling**: `t2 = t1 * (D2 / D1)`. NO Riegel power-law, NO
  fatigue factor — the user explicitly deferred those. Don't reintroduce them.

## 4. The task

Build the read-only, cohort-aware query surface over `clean_results`. Two dbt
models + the Python read layer + tests. **No modeled/extrapolated table this
stage** (`field_pr_equivalent` is deferred to Stage 3, designed alongside the
comparison representation).

### 4A. dbt marts (`dbt/models/`)

`clean_results` schema (the source — VARCHAR ranks are intentional):
```
raceID VARCHAR, seriesID BIGINT, year BIGINT, series_name VARCHAR,
continent VARCHAR, athleteID VARCHAR, name VARCHAR, country VARCHAR,
gender VARCHAR (values 'Male'/'Female'), division VARCHAR,
is_age_group BOOLEAN, is_pro BOOLEAN,
overall_seconds INTEGER, swim_seconds INTEGER, bike_seconds INTEGER,
run_seconds INTEGER  (segment seconds may be NULL — nulled outliers),
overall_rank VARCHAR, division_rank VARCHAR
```

1. **`stg_results`** (materialized: view) — `SELECT FROM clean_results`, add a
   canonical `cohort` column using the same CASE logic as
   `cohort_sizing.py::cohort_case_sql()`: `MPRO`/`FPRO` pass through; exact
   `{gender}{band}` matches pass through; everything else → `NULL`. Add
   `is_official` (cohort IS NOT NULL). Bands come from a dbt var
   (`var('official_age_bands')` etc.), defaulted in `dbt_project.yml` to mirror
   `config.OFFICIAL_AGE_BANDS`. Normalize `gender` to `M`/`F` here if helpful
   for cohort matching (raw is `Male`/`Female`).
2. **`fct_results`** (materialized: table) — the analysis grain: one row per
   (raceID, athleteID) finisher, columns: `raceID, athleteID, year, cohort,
   gender, is_official, is_pro, overall_seconds, swim_seconds, bike_seconds,
   run_seconds`. This is what the percentile tool reads.

### 4B. dbt schema tests (`dbt/models/*.yml`)
- `not_null`: raceID, overall_seconds on `fct_results` (hard, error-level).
  **athleteID**: ~7% of source rows have no athleteID — a structural gap in the
  scrape, not a cleaning error — so its `not_null` test is **warn-level**
  (`severity: warn`); it documents the gap (currently 60,944 rows) rather than
  failing the build.
- `accepted_values`: `gender` in (M, F); spot-check `cohort` includes the
  official set.
- range/`dbt_utils`-style or singular tests: `overall_seconds` within the
  cleaner's bounds (7h..19h = 25200..68400); segment seconds within their
  documented bounds when not null (see `clean_data.py` constants).

### 4C. Read-only access layer (`src/howmid/data/`)
3. **`connection.py`** — implement `read_only_connection()` (currently a stub):
   a context manager yielding `duckdb.connect(str(config.DB_PATH),
   read_only=True)`, closed on exit. Guard layer 1.
4. **`queries.py`** — implement typed, parameterized read helpers the percentile
   tool will call. At minimum:
   - `cohort_size(cohort, discipline) -> int`
   - `cohort_segment_seconds(cohort, discipline) -> list[int]` (non-null only)
   - `cohort_median_seconds(cohort, discipline) -> float | None`
   Parameterized queries only — never f-string user input into SQL.

### 4D. Tests (`tests/`)
5. `test_connection.py` — `read_only_connection()` yields a working read
   connection AND rejects writes (a `CREATE TABLE`/`INSERT` raises).
6. `test_queries.py` — assert against known truth from
   `data/cohort_sizing.json`: e.g. `cohort_size('MPRO','run')` is consistent
   with MPRO=8678 (allow for null-segment coverage), a known age-group cell
   returns >0, and a sub-min cell (one of the 3 below `MIN_COHORT_SIZE`) is
   handled. Read `cohort_sizing.json` in the test rather than hard-typing.

## 5. Definition of done

All must pass. **dbt must run from inside `dbt/`** — `profiles.yml` points at
`../data/howmid.duckdb`, a path relative to the dbt project dir, so running from
the repo root resolves the warehouse to the wrong location and errors.
```bash
# dbt (run from the dbt/ dir so the relative profile path resolves)
(cd dbt && uv run dbt run  --project-dir . --profiles-dir .)   # builds stg_results + fct_results
(cd dbt && uv run dbt test --project-dir . --profiles-dir .)   # schema tests green

# the rest run from the repo root
uv run pytest tests/                                     # connection + queries
./scripts/check_invariants.sh                            # Invariant 1 green
uv run ruff check src/ tests/                            # lint clean
```
- `field_pr_equivalent` is NOT built (deferred — do not add it).
- `RIEGEL_EXPONENT` / `FATIGUE_FACTOR` remain unreferenced.

## 6. Out of scope (do not touch)
- Extrapolation/percentile **logic** (Stage 3).
- Anything under `agent/`, `llm.py`, `guardrails/grounding.py`,
  `guardrails/input_validation.py`, `app/`, `eval/`.
- `scripts/clean_data.py` / `cohort_sizing.py` — leave as-is (only their
  `--db` defaults already point at `data/`).

## 7. Open decision pushed to Stage 3 (context, not your job now)
`field_pr_equivalent` needs a **comparison representation** — fixed everyday
reference distances (implied 5k/10k/40k/1500m) vs. storing **pace** (sec/km).
Undecided on purpose; the user deferred it. Build Stage 2 without it.
```
