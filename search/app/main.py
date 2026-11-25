from contextlib import asynccontextmanager

from fastapi import FastAPI
from google.adk.sessions import BaseSessionService, DatabaseSessionService

from app.adapters.inbound.api.routes import router
from app.adapters.inbound.login.google_login import GoogleLogin, login_router, require_login
from app.adapters.inbound.request_log import log_request, setup_request_logging
from app.adapters.outbound.agent.adk_agent import AdkAgent
from app.adapters.outbound.db.pg_user_directory import PgUserDirectory
from app.adapters.outbound.db.pgvector_search import PgVectorSearch
from app.adapters.outbound.db.pool import open_pool
from app.adapters.outbound.embeddings.fastembed_embedder import FastEmbedEmbedder
from app.adapters.outbound.llm.litellm_llm import LiteLLMAdapter
from app.adapters.outbound.llm.mock_llm import MockLLM
from app.application.ask_agent import AskAgent
from app.application.ask_question import AskQuestion
from app.application.ports.llm import LLMPort
from app.application.search_docs import SearchDocs
from app.settings import Settings

settings = Settings()
setup_request_logging()


def create_llm(settings: Settings) -> LLMPort:
    api_key = settings.llm_api.get_secret_value()
    if not api_key:
        return MockLLM()
    return LiteLLMAdapter(
        settings.llm_model, settings.llm_fallback_model, api_key, settings.llm_reasoning_effort
    )


def create_agent(settings: Settings, sessions: BaseSessionService) -> AdkAgent | None:
    api_key = settings.llm_api.get_secret_value()
    if not api_key:
        return None
    return AdkAgent(
        settings.llm_model,
        settings.llm_fallback_model,
        api_key,
        settings.llm_reasoning_effort,
        settings.agent_max_llm_calls,
        sessions,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await open_pool(
        settings.database_url.get_secret_value(), settings.db_pool_size, settings.db_pool_timeout
    )
    app.state.users = PgUserDirectory(pool)
    vectors = PgVectorSearch(pool, settings.search_candidates, settings.rrf_k)
    embedder = FastEmbedEmbedder(settings.embedding_model_path)
    search_docs = SearchDocs(embedder, vectors, settings.top_k, settings.min_score)
    app.state.ask_question = AskQuestion(search_docs, create_llm(settings))

    sessions = DatabaseSessionService(
        db_url=settings.database_url.get_secret_value().replace(
            "postgresql://", "postgresql+psycopg://", 1
        ),
        pool_size=settings.session_pool_size,
        max_overflow=0,
    )
    app.state.ask_agent = None
    agent = create_agent(settings, sessions)
    if agent is not None:
        app.state.ask_agent = AskAgent(agent, search_docs, vectors)

    yield
    await sessions.close()
    await pool.close()


app = FastAPI(lifespan=lifespan)
app.state.google_login = GoogleLogin(settings.google_client_id)
app.include_router(login_router)
app.middleware("http")(require_login)
app.middleware("http")(log_request)
app.include_router(router)
app.include_router(router, prefix="/api/v1")
