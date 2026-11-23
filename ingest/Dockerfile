FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
RUN useradd --create-home app
USER app
WORKDIR /home/app

ENV PATH="/home/app/.venv/bin:$PATH" UV_NO_CACHE=1 FASTEMBED_CACHE_PATH=/home/app/models
COPY --chown=app pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('google/embeddinggemma-300m')"
COPY --chown=app . .

CMD ["python", "ingest.py"]
