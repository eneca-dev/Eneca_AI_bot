from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # OpenAI Configuration
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    # Supabase Configuration
    supabase_url: Optional[str] = Field(None, alias="SUPABASE_URL")
    supabase_key: Optional[str] = Field(None, alias="SUPABASE_KEY")

    # Bot Configuration
    bot_token: Optional[str] = Field(None, alias="BOT_TOKEN")

    # Application Settings
    debug: bool = Field(True, alias="DEBUG")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    environment: str = Field("development", alias="ENVIRONMENT")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
