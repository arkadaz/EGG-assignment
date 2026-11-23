FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
WORKDIR /app

ENV UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

FROM python:3.12-slim

RUN useradd --create-home app
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
COPY --from=build /app/.venv .venv
COPY app app

USER app
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
