from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Ghostfolio
    ghostfolio_api_url: str = "http://localhost:3333"
    ghostfolio_access_token: str = ""

    # LLM
    anthropic_api_key: str = ""

    # Observability
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "ghostfolio-trading-agent"

    # Agent
    agent_port: int = 8000
    cache_ttl_seconds: int = 300

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
