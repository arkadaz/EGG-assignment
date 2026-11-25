# EGG RAG

A question-answering service over 10 Wikipedia articles. It finds the passages that match a
question (RAG with pgvector and PostgreSQL full-text search) and has an LLM answer from those
passages, with the sources attached.

It is three projects that share only the database, plus the Terraform that deploys them:

| Folder | What it does | Runs as |
|---|---|---|
| [`migrate/`](migrate) | `migrate.py` applies the SQL files in `migrations/` in name order. It records each file in a `schema_migrations` table, so a file is applied only once. Then it adds `ALLOWED_EMAIL` to the `users` table as the first user. | A job that runs before ingest and exits. |
| [`ingest/`](ingest) | `ingest.py` reads `data/wikipedia.jsonl`, splits each article into paragraphs, embeds them and stores the documents and chunks in PostgreSQL. A SHA-256 hash of every document and chunk lets it skip what is already stored. | A job that runs and exits. |
| [`search/`](search) | `POST /ask`: hybrid search and an LLM answer with sources. `POST /agent/ask`: a Google ADK agent that can search several times before it answers, and keeps each user's chats in Postgres. Every route needs a Google login, and only emails in the `users` table can sign in. Each request is logged as one JSON line. | A FastAPI service. |
| [`infrastructure/`](infrastructure) | Terraform for GCP: Cloud SQL, Cloud Run, Secret Manager. It also deploys the images and runs the migrate and ingest jobs. Its state is kept in a GCS bucket. | GitHub Actions only, when you start Deploy or Destroy. Locally, Docker Compose runs everything instead. |

The contract between the projects is the schema in
[`migrate/migrations/`](migrate/migrations) and the embedding model
`google/embeddinggemma-300m`, named in both [`ingest/ingest.py`](ingest/ingest.py) and
[`fastembed_embedder.py`](search/app/adapters/outbound/embeddings/fastembed_embedder.py).
The two model names must stay the same.

Stack:

- Python 3.12 with uv, FastAPI, Docker Compose
- PostgreSQL 16 with pgvector (HNSW cosine index) and full-text search (GIN index)
- Embeddings: `google/embeddinggemma-300m` through fastembed (ONNX). It runs inside the
  containers, produces 768 numbers per text and needs no API key. The model files (1.2 GB) are
  not in the images:
  - **On GCP:** they are read from a Cloud Storage bucket mounted at `/models`.
  - **Locally:** they are read from the `models/` folder.
- LLM through LiteLLM: the free `openrouter/nvidia/nemotron-3.5-lightning:free`, falling back to
  `openrouter/z-ai/glm-5.3-flash` when it fails, or a mock LLM when no `LLM_API` key is set
- Agent: Google ADK
- Dataset: 10 Wikipedia articles (CC BY-SA 4.0), 330 paragraphs

How it works and how it runs on GCP: [ARCHITECTURE.md](ARCHITECTURE.md). How to set up GCP and
GitHub and deploy it yourself, step by step: [DEPLOY.md](DEPLOY.md).

## Run locally

You need Docker.

First get the embedding model once into `models/embeddinggemma-300m`. Git ignores this folder.
Copy it from the project's bucket:

```bash
gcloud storage cp -r gs://egg-interview-models/embeddinggemma-300m models/
```

If you have no access to that bucket, download it from Hugging Face instead. The version is pinned
to the one this project was tested with:

```bash
uvx --from huggingface_hub huggingface-cli download onnx-community/embeddinggemma-300m-ONNX \
  config.json special_tokens_map.json tokenizer.json tokenizer_config.json \
  onnx/model.onnx onnx/model.onnx_data \
  --revision 5090578d9565bb06545b4552f76e6bc2c93e4a66 --local-dir models/embeddinggemma-300m
```

Then start everything:

```bash
cp .env.example .env
docker compose up --build
```

In `.env`, set:

- `POSTGRES_PASSWORD`: letters and digits
- `ALLOWED_EMAIL`: your Google account. migrate adds it to the `users` table as the first user.
- `GOOGLE_CLIENT_ID`: the OAuth client ID. Step 7 of [DEPLOY.md](DEPLOY.md) shows how to create
  it. Add `http://localhost` and `http://localhost:8000` to its JavaScript origins.
- `LLM_API` (optional): an OpenRouter key. Without it, `/ask` uses the mock LLM and the agent is
  off.

Git ignores `.env`. migrate does not run without `ALLOWED_EMAIL`, and search does not start without
`GOOGLE_CLIENT_ID`.

Compose mounts `models/` read-only into ingest and search, so nothing downloads the model during
a build or a start. Each service starts once the one before it is done:

1. `db` starts and becomes healthy.
2. `migrate` creates the tables, adds `ALLOWED_EMAIL` to the `users` table, and exits.
3. `ingest` loads the data and exits.
4. `search` starts.

```
migrate-1  | 001_create_tables.sql: applied
migrate-1  | 002_create_users.sql: applied
migrate-1  | first user: in the users table
ingest-1   | Documents: 10 new, 0 duplicates skipped
ingest-1   | Chunks: 330 new, 0 duplicates skipped
```

Open http://localhost:8000/docs. It sends you to the login page. Sign in with Google as
`ALLOWED_EMAIL`, and you land back on `/docs`, the API. Use "Try it out" there, because your login
comes with it. http://localhost:8000/logout signs you out.

### Users

Only emails in the `users` table can sign in. Add or remove someone with SQL; it works on their
next request, with no restart:

```bash
docker compose exec db psql -U rag -d rag \
  -c "INSERT INTO users (email) VALUES ('friend@example.com')"
docker compose exec db psql -U rag -d rag \
  -c "DELETE FROM users WHERE email = 'friend@example.com'"
```

Write the email in lower case. The only role is `user` for now; the column is there for more roles
later. While the Google sign-in app is in Testing mode, a new person must also be a test user in
Google Auth Platform.

### Ask a question

Every route except `/login`, `/auth/google` and `/logout` needs the login:

- Without it, an API call gets 401 `Login required`, and a page sends you to `/login`.
- The login is the `google_id_token` cookie, a JWT signed by Google that lasts one hour.

To call the API from curl, copy that cookie from the browser. It is under the developer tools,
in Application → Cookies.

```bash
curl -X POST localhost:8000/ask -H "Content-Type: application/json" \
  -b "google_id_token=<the cookie value>" \
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
  "prompt_version": "v1",
  "session_id": null
}
```

`score` is the cosine similarity between the question and the passage. The sources are in hybrid
search order. `prompt_version` says which version of the prompts in
[`prompts.py`](search/app/application/prompts.py) produced the answer. `session_id` is only set by
`/agent/ask`.

| Request | Result |
|---|---|
| A question the dataset cannot answer, such as `What is the best pizza topping?` | `"I could not find information about that in the knowledge base."` with no sources. The LLM is not called. |
| `POST /agent/ask` with the same body | The agent's answer, the passages it used, and a `session_id`. Without `LLM_API` it returns 503 `The agent needs an LLM_API key`. |
| `POST /agent/ask` with `"session_id"` from an earlier answer | The agent continues that chat: it sees the earlier questions and answers. The chat is stored in Postgres under the signed-in email, so it survives a restart, and another user cannot continue it. |
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

All three projects read environment variables. `search` also reads a `.env` file inside
`search/`; see
[`search/.env.example`](search/.env.example). Nothing secret is in the code or the images. Compose
takes `POSTGRES_PASSWORD` and `LLM_API` from the git-ignored `.env`. `search` holds
`DATABASE_URL` and `LLM_API` as `SecretStr`, so printing the settings shows `**********`. On GCP
they come from Secret Manager.

| Variable | Used by | Default |
|---|---|---|
| `POSTGRES_PASSWORD` | compose | required |
| `DATABASE_URL` | all three | required (compose builds it from `POSTGRES_PASSWORD`) |
| `ALLOWED_EMAIL` | migrate | required, the first user, added to the `users` table |
| `GOOGLE_CLIENT_ID` | search | required, the OAuth client ID that Google signs the login JWT for |
| `DB_POOL_SIZE` / `DB_POOL_TIMEOUT` | search | `5` / `10` seconds |
| `SESSION_POOL_SIZE` | search | `2` connections for the agent's chats |
| `TOP_K` | search | `4` passages per answer |
| `MIN_SCORE` | search | `0.4`, passages below this cosine similarity are dropped |
| `SEARCH_CANDIDATES` / `RRF_K` | search | `20` / `60`, hybrid search candidates per side and the RRF constant |
| `LLM_API` | search | empty: the mock LLM. Set: an OpenRouter key for the real LLM. |
| `LLM_MODEL` | search | `openrouter/nvidia/nemotron-3.5-lightning:free` (any LiteLLM model name) |
| `LLM_FALLBACK_MODEL` | search | `openrouter/z-ai/glm-5.3-flash`, used when `LLM_MODEL` fails |
| `LLM_REASONING_EFFORT` | search | `low` |
| `AGENT_MAX_LLM_CALLS` | search | `6`, the most LLM calls the agent makes per question |
| `DATASET_PATH` / `MIN_PARAGRAPH_LENGTH` | ingest | `data/wikipedia.jsonl` / `80` characters |
| `EMBEDDING_MODEL_PATH` | ingest and search | `/models/embeddinggemma-300m`, the folder with the model files |

`MIN_SCORE` is 0.4 because of measured scores on this dataset. Questions the articles answer score
0.60 to 0.72; unrelated questions score 0.09 to 0.19.

## Logs

search writes one JSON line to stdout for every request. Cloud Logging reads it as a structured
entry:

```json
{"severity": "INFO", "time": "2026-11-25T08:15:02.481+00:00", "message": "POST /agent/ask 200", "request_id": "6f1c2a0e-...", "method": "POST", "path": "/agent/ask", "status": 200, "duration_ms": 2843, "user": "you@example.com"}
```

- **`request_id`** comes from the `X-Request-ID` header when the caller sends one, otherwise it is
  a new UUID. The response sends it back in `X-Request-ID`.
- **`user`** is the signed-in email, or `null` before login.
- **A failed request** is logged as `ERROR`, with `error` and `traceback`.

Uvicorn's own access log is off, so each request appears once.

## Tests and lint

```bash
cd search
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

`ingest/` and `migrate/` have no tests. Lint each of them the same way, for example `ingest/`:

```bash
cd ingest
uv sync
uv run ruff check .
uv run ruff format --check .
```

```bash
cd infrastructure
terraform fmt -check
terraform init -backend=false
terraform validate
```

The tests replace the database, the model and the LLM with fakes, so they need nothing else
running. They sign in with JWTs signed by a test key made fresh for each run, instead of
Google's.

[`test_api.py`](search/tests/test_api.py) checks that:

- `/ask` and `/api/v1/ask` return only passages above `MIN_SCORE`
- a question with no match gets the "not found" answer
- the agent lists each passage once
- the agent continues the chat whose `session_id` it is given
- each user has their own chats
- `/agent/ask` returns 503 without a key
- the prompt numbers the passages

[`test_login.py`](search/tests/test_login.py) checks that:

- an API call without the login gets 401, and a page goes to `/login`
- the owner can sign in and out
- a user added to the `users` table can sign in at once, and a removed one is locked out at once
- every other token is refused: an account not in the table, an unverified email, another client
  ID, another issuer, an expired token, a forged signature, or junk

[`test_request_log.py`](search/tests/test_request_log.py) checks that each request is logged as
JSON with its request id and user, and that an error is logged with its traceback.

There are three workflows in [`.github/workflows/`](.github/workflows):

| Workflow | Starts | What it does |
|---|---|---|
| `ci.yml` | on every push and pull request | the commands above, plus a Docker build of all three images |
| `deploy.yml` | only when you click Run workflow | builds and pushes the three images, then `terraform apply`, which runs the migrate job, then the ingest job, then moves search to the new image |
| `destroy.yml` | only when you click Run workflow | Terraform destroy, which removes everything it created |

## Structure

`migrate/` and `ingest/` are one script each. `search/` uses a hexagonal (ports and adapters)
layout:

```
search/app/
  domain/models.py                 Passage, Answer
  application/search_docs.py       embed the question -> hybrid search -> keep score >= MIN_SCORE
  application/ask_question.py      use case: search_docs -> LLM, or "not found" without the LLM
  application/ask_agent.py         use case: agent with search_knowledge_base and list_documents tools
  application/prompts.py           the shared prompts and PROMPT_VERSION
  application/ports/               EmbedderPort, VectorSearchPort, LLMPort, AgentPort, UserDirectoryPort
  adapters/inbound/api/            POST /ask and /agent/ask (also under /api/v1), use cases via Depends
  adapters/inbound/login/          Google sign-in page, JWT check, users table lookup, middleware that guards every route
  adapters/inbound/request_log.py  one JSON log line per request
  adapters/outbound/db/            connection pool, PgVectorSearch (hybrid search with RRF), PgUserDirectory (users table)
  adapters/outbound/embeddings/    FastEmbedEmbedder (EmbeddingGemma)
  adapters/outbound/llm/           LiteLLMAdapter (real LLM), MockLLM (no key)
  adapters/outbound/agent/         AdkAgent: a Google ADK LlmAgent on the same LiteLLM models
  main.py                          wiring: lifespan builds everything once
  settings.py                      every setting, read once at startup

migrate/
  migrate.py                       apply each new file in migrations/ and record it, then add the first user
  migrations/001_create_tables.sql documents, chunks, the HNSW and full-text indexes
  migrations/002_create_users.sql  users who may sign in, with a role

ingest/
  ingest.py                        hash -> skip what is stored -> embed new paragraphs -> insert
  data/wikipedia.jsonl

infrastructure/                    Terraform, one file per area
  main.tf                          providers and the GCS state bucket
  database.tf                      Cloud SQL instance, database and user
  secrets.tf                       DATABASE_URL secret, the existing llm-api secret
  service_accounts.tf              one account for the jobs, one for search, and their access
  cloud_run.tf                     migrate job, ingest job, search service, all on the image_tag images
```

To change the schema, add a new file such as `migrate/migrations/003_add_column.sql`. Never edit
a file that has already been applied.

In `search/`, imports only point inward: `adapters` → `application` → `domain`.

## Design patterns

- **Hexagonal (ports and adapters):** the use cases in `application/` depend only on the ports in
  `application/ports/`. The database, model, LLM and agent framework are adapters in `adapters/`
  and can be swapped without touching the use cases.
- **Repository:** `PgVectorSearch` keeps the search SQL behind `VectorSearchPort`, and
  `PgUserDirectory` keeps the users lookup behind `UserDirectoryPort`. Hybrid search merges
  pgvector cosine ranking and Postgres full-text ranking with Reciprocal Rank Fusion.
- **Factory:** `create_llm` in `main.py` returns `LiteLLMAdapter` when `LLM_API` is set, else
  `MockLLM`. `create_agent` returns `AdkAgent` or `None`.
- **Strategy:** `LiteLLMAdapter` and `MockLLM` are two interchangeable answers to `LLMPort`.
- **Dependency injection:** `lifespan` builds the use cases once. Routes receive them through
  `Depends(get_ask_question)` and `Depends(get_ask_agent)`, and the tests replace them with fakes.
- **One shared resource:** one connection pool, one small pool for the agent's chats and one
  embedding model per process, created in `lifespan` and closed on shutdown.
