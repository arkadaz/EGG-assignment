from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr
    google_client_id: str = Field(min_length=1)
    embedding_model_path: str = "/models/embeddinggemma-300m"
    db_pool_size: int = 5
    db_pool_timeout: float = 10.0
    session_pool_size: int = 2
    top_k: int = 4
    min_score: float = 0.4
    search_candidates: int = 20
    rrf_k: int = 60
    llm_api: SecretStr = SecretStr("")
    llm_model: str = "openrouter/nvidia/nemotron-3.5-lightning:free"
    llm_fallback_model: str = "openrouter/z-ai/glm-5.3-flash"
    llm_reasoning_effort: str = "low"
    agent_max_llm_calls: int = 6
