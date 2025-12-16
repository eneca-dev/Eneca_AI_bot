from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from pathlib import Path
import os

# Get absolute path to project root (.env location)
_CONFIG_DIR = Path(__file__).parent.parent
_ENV_FILE = _CONFIG_DIR / ".env"

# Debug: Print .env path at module load time
print(f"DEBUG: Loading .env from: {_ENV_FILE}")
print(f"DEBUG: .env exists: {_ENV_FILE.exists()}")


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # OpenAI Configuration
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    # Supabase Configuration - DEV/PROD Separation
    # DEV Supabase - for RAG (documents table)
    supabase_rag_url: Optional[str] = Field(None, alias="SUPABASE_RAG_URL")
    supabase_rag_key: Optional[str] = Field(None, alias="SUPABASE_RAG_KEY")

    # PROD Supabase - for chat (chat_messages table)
    supabase_chat_url: Optional[str] = Field(None, alias="SUPABASE_CHAT_URL")
    supabase_chat_key: Optional[str] = Field(None, alias="SUPABASE_CHAT_KEY")  # ANON_KEY for Realtime subscriptions
    supabase_chat_service_key: Optional[str] = Field(None, alias="SUPABASE_CHAT_SERVICE_KEY")  # Bypasses RLS for bot writes

    # MCP Server Configuration
    mcp_server_url: str = Field(..., alias="MCP_SERVER_URL")

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
    agent_max_iterations: int = Field(10, alias="AGENT_MAX_ITERATIONS")
    agent_timeout: int = Field(300, alias="AGENT_TIMEOUT")

    # Embedding & Vector Store Configuration
    embedding_model: str = Field("text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dimensions: int = Field(1536, alias="EMBEDDING_DIMENSIONS")
    vector_search_k: int = Field(5, alias="VECTOR_SEARCH_K")
    # Similarity threshold: 0.7-0.9 for high-quality matches (lowered to 0.35 if encoding issues exist)
    similarity_threshold: float = Field(0.7, alias="SIMILARITY_THRESHOLD")

    # Memory Configuration
    enable_conversation_memory: bool = Field(default=True, alias="ENABLE_CONVERSATION_MEMORY")
    memory_type: str = Field(default="memory", alias="MEMORY_TYPE")  # Options: "memory", "sqlite", "postgres", "redis"
    memory_db_path: str = Field(default="data/checkpoints.db", alias="MEMORY_DB_PATH")

    # PostgreSQL Configuration (for PostgreSQL checkpointer)
    # Note: Supabase PostgreSQL connection uses the following format:
    # postgresql://postgres.[PROJECT_REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres
    postgres_connection_string: Optional[str] = Field(None, alias="POSTGRES_CONNECTION_STRING")

    # Supabase Memory Configuration (when MEMORY_TYPE=supabase)
    # Uses n8n_chat_histories table for conversation persistence
    memory_supabase_table: str = Field("n8n_chat_histories", alias="MEMORY_SUPABASE_TABLE")

    class Config:
        # Use absolute path to ensure .env is found regardless of working directory
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields in .env


# Global settings instance
settings = Settings()
