"""
Configuration management for Eneca AI Bot.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Bot Configuration
    bot_token: str
    bot_platform: Literal["telegram", "discord"] = "telegram"

    # Supabase Configuration
    supabase_url: str
    supabase_key: str
    supabase_service_key: str | None = None

    # LLM Provider Configuration
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None

    # LangChain Configuration
    langchain_tracing_v2: bool = False
    langchain_api_key: str | None = None
    langchain_project: str = "eneca-ai-bot"

    # Application Settings
    debug: bool = False
    log_level: str = "INFO"
    environment: Literal["development", "staging", "production"] = "development"

    # Agent Configuration
    agent_max_iterations: int = 10
    agent_timeout: int = 300


# Global settings instance
settings = Settings()
