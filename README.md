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
