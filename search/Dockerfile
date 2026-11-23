FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
WORKDIR /app

ENV UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1 FASTEMBED_CACHE_PATH=/app/models
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
RUN .venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('google/embeddinggemma-300m')"

FROM python:3.12-slim

RUN useradd --create-home app
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" FASTEMBED_CACHE_PATH=/app/models
COPY --from=build /app/.venv .venv
COPY --from=build --chown=app /app/models models
COPY app app

USER app
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
