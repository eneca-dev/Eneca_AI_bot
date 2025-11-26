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

    # API Security
    api_key: Optional[str] = Field(None, alias="API_KEY")
    api_key_header: str = Field("X-API-Key", alias="API_KEY_HEADER")

    # Application Settings
    debug: bool = Field(True, alias="DEBUG")
    log_level: str = Field("DEBUG", alias="LOG_LEVEL")
    environment: str = Field("development", alias="ENVIRONMENT")

    # Agent Configuration
    orchestrator_model: str = Field("gpt-4o", alias="ORCHESTRATOR_MODEL")
    orchestrator_temperature: float = Field(0.7, alias="ORCHESTRATOR_TEMPERATURE")
    rag_agent_model: str = Field("gpt-4o", alias="RAG_AGENT_MODEL")
    rag_agent_temperature: float = Field(0.3, alias="RAG_AGENT_TEMPERATURE")
    max_agent_iterations: int = Field(5, alias="MAX_AGENT_ITERATIONS")

    # Embedding & Vector Store Configuration
    embedding_model: str = Field("text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(1536, alias="EMBEDDING_DIMENSIONS")
    vector_search_k: int = Field(5, alias="VECTOR_SEARCH_K")
    # Similarity threshold: 0.7-0.9 for high-quality matches (lowered to 0.35 if encoding issues exist)
    similarity_threshold: float = Field(0.7, alias="SIMILARITY_THRESHOLD")

    # Memory Configuration
    enable_conversation_memory: bool = Field(True, alias="ENABLE_CONVERSATION_MEMORY")
    memory_type: str = Field("memory", alias="MEMORY_TYPE")  # Options: "memory", "sqlite", "postgres", "redis"
    memory_db_path: str = Field("data/checkpoints.db", alias="MEMORY_DB_PATH")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env


# Global settings instance
settings = Settings()
