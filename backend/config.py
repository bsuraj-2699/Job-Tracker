"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings, sourced from the environment / .env.

    Field names map to upper-cased env vars (e.g. ``groq_api_key`` reads
    ``GROQ_API_KEY``).
    """

    groq_api_key: str = ""
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "job_applications"
    primary_model: str = "openai/gpt-oss-120b"
    fallback_model: str = "qwen/qwen3.6-27b"
    reminder_check_interval_hours: int = 24
    follow_up_after_days: int = 7

    # LangSmith / LangChain tracing
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "jobtrack-agent"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Single shared settings instance imported across the app.
settings = Settings()
