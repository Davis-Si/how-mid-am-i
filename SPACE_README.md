---
title: How Mid Am I?
emoji: 🏊🚴🏃
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# How Mid Am I?

Tell it your everyday swim/bike/run PRs; it projects them onto an Ironman and
tells you how mid you are vs. the real field. Every percentile is computed from
886,768 real Ironman finishers; every projected time is a labelled estimate.

> **This file is the Hugging Face Space README.** Its YAML front-matter tells
> Spaces to build the repo's `Dockerfile` and serve on port 7860. When pushing
> to the Space, copy this to the Space repo's `README.md`.

## Deploy notes (Docker Space)

- **Runtime:** the `Dockerfile` builds with uv (core + `app` extras) and copies
  the prebuilt `data/howmid.duckdb` into the image.
- **The warehouse must be present in the Space repo.** The main project
  `.gitignore` ignores `data/*.duckdb` (it's reproducible locally), but the
  Space SHIPS it. In the Space repo:
  ```bash
  git lfs install
  git lfs track "data/*.duckdb"
  git add .gitattributes data/howmid.duckdb
  ```
  (The Space repo should NOT ignore `data/howmid.duckdb`.)
- **Secret:** add `ANTHROPIC_API_KEY` in the Space's Settings → Secrets. Never
  commit it.
- **Cost backstop:** set an account spend limit in the Anthropic Console BEFORE
  making the Space public.
