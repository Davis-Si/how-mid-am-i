# How Mid Am I? — one image for local, HF Spaces (Docker SDK), and Fly/Cloud Run.
# FR-25: one-command run. The built warehouse is COPYed in (static historical
# data); the raw CSV is excluded via .dockerignore (not needed at runtime).

FROM python:3.12-slim

# uv for fast, reproducible installs from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install deps first (better layer caching). Core + app extras only — no dev,
# no dbt (the warehouse is prebuilt and shipped, not rebuilt here).
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --extra app

# App code + the prebuilt read-only warehouse.
COPY app/ ./app/
COPY data/howmid.duckdb ./data/howmid.duckdb

# config.DB_PATH resolves to <project root>/data/howmid.duckdb by default, which
# matches this layout; set explicitly to be safe across hosts.
ENV HOWMID_DB=/app/data/howmid.duckdb
# ANTHROPIC_API_KEY is injected at runtime (HF Space secret / -e flag), never baked.

EXPOSE 7860

CMD ["uv", "run", "--no-dev", "python", "app/chat.py"]
