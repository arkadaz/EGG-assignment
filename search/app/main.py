from contextlib import asynccontextmanager

from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from app.adapters.inbound.adk_ui.agent_loader import SingleAgentLoader
from app.adapters.inbound.api.routes import router
from app.adapters.outbound.agent.adk_agent import AdkAgent
from app.adapters.outbound.db.pgvector_search import PgVectorSearch
from app.adapters.outbound.db.pool import open_pool
from app.adapters.outbound.embeddings.fastembed_embedder import FastEmbedEmbedder
from app.adapters.outbound.llm.litellm_llm import LiteLLMAdapter
from app.adapters.outbound.llm.mock_llm import MockLLM
from app.application.ask_agent import AskAgent, KnowledgeBaseTools
from app.application.ask_question import AskQuestion
from app.application.ports.llm import LLMPort
from app.application.search_docs import SearchDocs
from app.settings import Settings

agent_loader = SingleAgentLoader()


def create_llm(settings: Settings) -> LLMPort:
    api_key = settings.llm_api.get_secret_value()
    if not api_key:
        return MockLLM()
    return LiteLLMAdapter(
        settings.llm_model, settings.llm_fallback_model, api_key, settings.llm_reasoning_effort
    )


def create_agent(settings: Settings) -> AdkAgent | None:
    api_key = settings.llm_api.get_secret_value()
    if not api_key:
        return None
    return AdkAgent(
        settings.llm_model,
        settings.llm_fallback_model,
        api_key,
        settings.llm_reasoning_effort,
        settings.agent_max_llm_calls,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    pool = await open_pool(
        settings.database_url.get_secret_value(), settings.db_pool_size, settings.db_pool_timeout
    )
    vectors = PgVectorSearch(pool, settings.search_candidates, settings.rrf_k)
    search_docs = SearchDocs(FastEmbedEmbedder(), vectors, settings.top_k, settings.min_score)
    app.state.ask_question = AskQuestion(search_docs, create_llm(settings))

    app.state.ask_agent = None
    agent = create_agent(settings)
    if agent is not None:
        app.state.ask_agent = AskAgent(agent, search_docs, vectors)
        agent_loader.agent = agent.build(KnowledgeBaseTools(search_docs, vectors).as_list())

    yield
    await pool.close()


app = get_fast_api_app(
    agents_dir=".",
    agent_loader=agent_loader,
    web=True,
    use_local_storage=False,
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(router, prefix="/api/v1")
