from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr
    db_pool_size: int = 5
    db_pool_timeout: float = 10.0
    top_k: int = 4
    min_score: float = 0.4
    search_candidates: int = 20
    rrf_k: int = 60
    llm_api: SecretStr = SecretStr("")
    llm_model: str = "openrouter/nvidia/nemotron-3.5-lightning:free"
    llm_fallback_model: str = "openrouter/z-ai/glm-5.3-flash"
    llm_reasoning_effort: str = "low"
    agent_max_llm_calls: int = 6
