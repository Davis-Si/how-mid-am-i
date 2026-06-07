# How Mid Am I?

A grounded conversational agent: tell it your everyday swim/bike/run PRs in
plain chat, and it projects them onto Ironman-equivalent performance and tells
you — with personality — exactly how mid you are versus the real Ironman field.

Every **percentile** is computed from real data by a deterministic tool; the
agent never invents a ranking. Every **extrapolated** figure is produced by a
documented model (Riegel + fatigue) and framed as an estimate, never a fact.

## Architecture

```
User (NL PRs) ─► LangGraph agent ─► answer (persona)
                  parse → extrapolate → percentile → synthesize → critic
                    │         │             │                        ▲
                  (LLM)   (pure math)   (SQL, read-only)        guardrails
                                              │
                                         DuckDB warehouse
                                   (clean_data.py + dbt marts)
```

**Number path / LLM path separation.** The math (`tools/`, `data/`) never
imports an LLM; the LLM (`llm.py`, `agent/`) never computes a number. Both
rules are enforced as greppable invariants (`scripts/check_invariants.sh`).

## Layout

| Path | Role |
|---|---|
| `data/` | raw Ironman CSVs + built `howmid.duckdb` (gitignored) |
| `scripts/clean_data.py` | raw CSV → `clean_results` (documented, verifiable) |
| `dbt/` | `clean_results` → marts (`fct_results`, `field_pr_equivalent`) |
| `src/howmid/` | the package: `config`, `tools`, `guardrails`, `agent`, `llm` |
| `app/` | Gradio chat UI + rate limit + spend cap |
| `eval/` | pandas oracle + ground-truth cases + report |
| `tests/` | pytest (extrapolation vs hand-calc, percentile vs oracle) |

## Quickstart

```bash
uv sync --extra dev          # reproducible install from uv.lock
uv run python -c "import howmid; print(howmid.__version__)"
```

## Eval results

_(populated by `eval/run_eval.py` once the harness is built — FR-22/23)_

## Data

Ironman 140.6 results, 2002–2024, sourced from Kaggle:
[**Ironman 140.6 Results Dataset (2002–2024)**](https://www.kaggle.com/datasets/miguswong/ironman-140-6-results-dataset-2002-2024)
by Migus Wong, originally scraped from
[coachcox.co.uk/imstats](https://www.coachcox.co.uk/imstats/).

- **~1.1M raw results → 886,768 clean finishers** across 587 races. Cleaning
  rules and counts are documented and verifiable — see `docs/DATA_CLEANING.md`
  and `data/cleaning_report.json`.
- **World Championship excluded.** This is the regular Ironman circuit, *not*
  Kona — so percentiles read as "faster than people who **finished** an
  Ironman," a fit but attainable peer group (never "vs. the general public").
- **The raw CSVs and the built DuckDB warehouse are not committed** (gitignored
  — large + third-party data). Download the dataset from the Kaggle link above
  into `data/`, then run `scripts/clean_data.py` to rebuild the warehouse.

The dataset belongs to its original authors and is used here for a
non-commercial, educational portfolio project. It is referenced, not
redistributed.

## License

Source code is licensed under the [MIT License](LICENSE). The license covers
the code only — **not** the Ironman dataset, which retains its own terms (see
**Data** above).
