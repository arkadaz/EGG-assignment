# EGG RAG

A question-answering service over 10 Wikipedia articles. It finds the passages that match a
question (RAG with pgvector and PostgreSQL full-text search) and has an LLM answer from those
passages, with the sources attached.

It is two projects that share only the database:

| Project | What it does | Runs as |
|---|---|---|
| [`ingest/`](ingest) | `ingest.py` reads `data/wikipedia.jsonl`, splits each article into paragraphs, embeds them and stores the documents and chunks in PostgreSQL. A SHA-256 hash of every document and chunk lets it skip what is already stored. | A job that runs once and exits. |
| [`search/`](search) | `POST /ask`: hybrid search and an LLM answer with sources. `POST /agent/ask`: a Google ADK agent that can search several times before it answers. `/`: the ADK web UI. | A FastAPI service. |

The contract between the two is the schema in [`db/init.sql`](db/init.sql) and the embedding model
`google/embeddinggemma-300m`, named in both [`ingest/ingest.py`](ingest/ingest.py) and
[`fastembed_embedder.py`](search/app/adapters/outbound/embeddings/fastembed_embedder.py).
The two must stay the same.

Stack:

- Python 3.12 with uv, FastAPI, Docker Compose
- PostgreSQL 16 with pgvector (HNSW cosine index) and full-text search (GIN index)
- Embeddings: `google/embeddinggemma-300m` through fastembed (ONNX). It runs inside the
  containers, produces 768 numbers per text and needs no API key.
- LLM through LiteLLM: the free `openrouter/nvidia/nemotron-3.5-lightning:free`, falling back to
  `openrouter/z-ai/glm-5.3-flash` when it fails, or a mock LLM when no `LLM_API` key is set
- Agent: Google ADK
- Dataset: 10 Wikipedia articles (CC BY-SA 4.0), 330 paragraphs

How it works and how it would run on GCP: [ARCHITECTURE.md](ARCHITECTURE.md).

## Run locally

You need Docker.

```bash
cp .env.example .env
docker compose up --build
```

In `.env`, set `POSTGRES_PASSWORD` (letters and digits). Optionally set `LLM_API` to an
OpenRouter key. Without it, `/ask` uses the mock LLM and the agent is off. Git ignores `.env`.

The first build downloads the 1.2 GB embedding model into each image, so it takes a few minutes.
Then Postgres applies `db/init.sql`, `ingest` loads the data and exits, and `search` starts:

```
ingest-1  | Documents: 10 new, 0 duplicates skipped
ingest-1  | Chunks: 330 new, 0 duplicates skipped
```

- http://localhost:8000/docs is the API.
- http://localhost:8000/ is the ADK web UI. It needs `LLM_API`. Pick `knowledge_agent`, ask a
  question and see each tool call (`search_knowledge_base`, `list_documents`) and its result.

### Ask a question

```bash
curl -X POST localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "Who created Kubernetes?"}'
```

The answer comes with the passages it was built from. Here it is shortened, with the mock LLM:

```json
{
  "answer": "[mock LLM] From \"Kubernetes\": Kubernetes was announced by Google on June 6, 2014. The project was conceived and created by Google employees Joe Beda, Brendan Burns, and Craig McLuckie. ...",
  "sources": [
    {
      "title": "Kubernetes",
      "source": "https://en.wikipedia.org/wiki/Kubernetes",
      "content": "Kubernetes was announced by Google on June 6, 2014. ...",
      "score": 0.671
    }
  ],
  "prompt_version": "v1"
}
```

`score` is the cosine similarity between the question and the passage. The sources are in hybrid
search order. `prompt_version` says which version of the prompts in
[`prompts.py`](search/app/application/prompts.py) produced the answer.

| Request | Result |
|---|---|
| A question the dataset cannot answer, such as `What is the best pizza topping?` | `"I could not find information about that in the knowledge base."` with no sources. The LLM is not called. |
| `POST /agent/ask` with the same body | The agent's answer and the passages it used. Without `LLM_API` it returns 503 `The agent needs an LLM_API key`. |
| An empty question or one over 1000 characters | 422 |

Every endpoint also works under `/api/v1`, for example `POST /api/v1/ask`.

### Load the data again

```bash
docker compose run --rm ingest
```

```
Documents: 0 new, 10 duplicates skipped
Chunks: 0 new, 330 duplicates skipped
```

Ingest only embeds what is new. If an article's text changes in `data/wikipedia.jsonl`, the next
run replaces that document and its chunks. Rebuild the image first with
`docker compose build ingest`, because the data file is inside the image. An article removed from
the file stays in the database.

### Stop

```bash
docker compose down -v
```

This stops everything and deletes the database.

## Configuration

Both projects read environment variables. `search` also reads a `.env` file inside `search/`; see
[`search/.env.example`](search/.env.example). Nothing secret is in the code or the images. Compose
takes `POSTGRES_PASSWORD` and `LLM_API` from the git-ignored `.env`. `search` holds
`DATABASE_URL` and `LLM_API` as `SecretStr`, so printing the settings shows `**********`. On GCP
they come from Secret Manager.

| Variable | Used by | Default |
|---|---|---|
| `POSTGRES_PASSWORD` | compose | required |
| `DATABASE_URL` | both | required (compose builds it from `POSTGRES_PASSWORD`) |
| `DB_POOL_SIZE` / `DB_POOL_TIMEOUT` | search | `5` / `10` seconds |
| `TOP_K` | search | `4` passages per answer |
| `MIN_SCORE` | search | `0.4`, passages below this cosine similarity are dropped |
| `SEARCH_CANDIDATES` / `RRF_K` | search | `20` / `60`, hybrid search candidates per side and the RRF constant |
| `LLM_API` | search | empty: the mock LLM. Set: an OpenRouter key for the real LLM. |
| `LLM_MODEL` | search | `openrouter/nvidia/nemotron-3.5-lightning:free` (any LiteLLM model name) |
| `LLM_FALLBACK_MODEL` | search | `openrouter/z-ai/glm-5.3-flash`, used when `LLM_MODEL` fails |
| `LLM_REASONING_EFFORT` | search | `low` |
| `AGENT_MAX_LLM_CALLS` | search | `6`, the most LLM calls the agent makes per question |
| `DATASET_PATH` / `MIN_PARAGRAPH_LENGTH` | ingest | `data/wikipedia.jsonl` / `80` characters |

`MIN_SCORE` is 0.4 because of measured scores on this dataset. Questions the articles answer score
0.60 to 0.72; unrelated questions score 0.09 to 0.19.

## Tests and lint

```bash
cd search
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

```bash
cd ingest
uv sync
uv run ruff check .
uv run ruff format --check .
```

The tests in [`search/tests/test_api.py`](search/tests/test_api.py) replace the database, the
model and the LLM with fakes, so they need nothing else running. They check that:

- `/ask` and `/api/v1/ask` return only passages above `MIN_SCORE`
- a question with no match gets the "not found" answer
- the agent lists each passage once
- `/agent/ask` returns 503 without a key
- the prompt numbers the passages

CI runs the same commands and builds both Docker images on every push:
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Structure

`ingest/` is one script. `search/` uses a hexagonal (ports and adapters) layout:

```
search/app/
  domain/models.py                 Passage, Answer
  application/search_docs.py       embed the question -> hybrid search -> keep score >= MIN_SCORE
  application/ask_question.py      use case: search_docs -> LLM, or "not found" without the LLM
  application/ask_agent.py         use case: agent with search_knowledge_base and list_documents tools
  application/prompts.py           the shared prompts and PROMPT_VERSION
  application/ports/               EmbedderPort, VectorSearchPort, LLMPort, AgentPort
  adapters/inbound/api/            POST /ask and /agent/ask (also under /api/v1), use cases via Depends
  adapters/inbound/adk_ui/         hands our agent to the ADK web UI
  adapters/outbound/db/            connection pool and PgVectorSearch (hybrid search with RRF)
  adapters/outbound/embeddings/    FastEmbedEmbedder (EmbeddingGemma)
  adapters/outbound/llm/           LiteLLMAdapter (real LLM), MockLLM (no key)
  adapters/outbound/agent/         AdkAgent: a Google ADK LlmAgent on the same LiteLLM models
  main.py                          wiring: lifespan builds everything once
  settings.py                      every setting, read once at startup

ingest/
  ingest.py                        hash -> skip what is stored -> embed new paragraphs -> insert
  data/wikipedia.jsonl
```

In `search/`, imports only point inward: `adapters` → `application` → `domain`.

## Design patterns

- **Hexagonal (ports and adapters):** the use cases in `application/` depend only on the ports in
  `application/ports/`. The database, model, LLM and agent framework are adapters in `adapters/`
  and can be swapped without touching the use cases.
- **Repository:** `PgVectorSearch` keeps all SQL behind `VectorSearchPort`. It runs hybrid search:
  pgvector cosine ranking and Postgres full-text ranking, merged with Reciprocal Rank Fusion.
- **Factory:** `create_llm` in `main.py` returns `LiteLLMAdapter` when `LLM_API` is set, else
  `MockLLM`. `create_agent` returns `AdkAgent` or `None`.
- **Strategy:** `LiteLLMAdapter` and `MockLLM` are two interchangeable answers to `LLMPort`.
- **Dependency injection:** `lifespan` builds the use cases once. Routes receive them through
  `Depends(get_ask_question)` and `Depends(get_ask_agent)`, and the tests replace them with fakes.
- **One shared resource:** one connection pool and one embedding model per process, created in
  `lifespan` and closed on shutdown.
