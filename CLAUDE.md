# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Eneca AI Bot is a RAG-enabled chatbot built with LangChain, Supabase (pgvector), and Python. It uses an orchestrator pattern to route between a general-purpose LLM and a specialized RAG agent for knowledge base queries. All prompts and user-facing messages are in Russian.

## Development Commands

### Environment Setup
```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/MacOS)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Bot
```bash
# CLI interface (standard version)
python app.py

# CLI interface with MCP support (async version)
python app_mcp.py

# Test orchestrator routing
python test_bot.py

# Test MCP integration
python test_mcp.py

# Debug Supabase vector search
python debug_supabase.py
```

### Configuration

Copy `.env.example` to `.env` and configure:
- `OPENAI_API_KEY` - Required for LLM and embeddings
- `SUPABASE_URL` and `SUPABASE_KEY` - Optional, bot runs without vector store
- `LOG_LEVEL` - Default: INFO

**MCP Configuration for Claude Code:**

Model Context Protocol (MCP) серверы настроены для Claude Code в `.mcp.json` (уровень проекта).

**Установленные MCP серверы:**
1. **context7** - Актуальная документация для библиотек (от Upstash)
2. **langchain-docs** - Официальная документация LangChain и LangGraph (mcpdoc)

**Requirements:**
- Node.js >= v18.0.0 (для context7)
- Python uv package manager (для mcpdoc): `pip install uv`

**Проверка работы:**
- Команда `/mcp` в Claude Code показывает список доступных серверов
- См. `.mcp-servers-info.md` для подробностей об инструментах

**Примечание:** Эти MCP серверы предназначены для Claude Code (для помощи в разработке), а не для бота.

## Architecture

### Multi-Agent System

The system implements a **three-tier agent hierarchy**:

1. **BaseAgent** (`agents/base.py`) - Abstract base class providing:
   - LangChain ChatOpenAI initialization (model, temperature)
   - System prompt loading from markdown files in `prompts/`
   - Common `invoke()` method for LLM calls

2. **OrchestratorAgent** (`agents/orchestrator.py`) - Main entry point:
   - Uses LangChain's `create_openai_functions_agent` with function calling
   - Routes simple queries directly, delegates complex queries to RAG agent
   - Implements `AgentExecutor` with max 5 iterations
   - System prompt: `prompts/orchestrator.md`

3. **RAGAgent** (`agents/rag_agent.py`) - Knowledge base specialist:
   - Performs vector similarity search via Supabase pgvector
   - Temperature: 0.3 (lower for factual responses)
   - Strict policy: answers ONLY from retrieved documents
   - System prompt: `prompts/rag_agent.md`

### Routing Mechanism

The orchestrator uses **LangChain function calling** (not manual conditionals):
- Tools registered in `_setup_tools()` with Russian-language descriptions
- LLM decides whether to answer directly or call appropriate tool
- Tool invocation → specialized agent/MCP server → formatted response → orchestrator finalizes

**Available tool categories:**
1. **RAG agent** (`knowledge_search`) - Internal knowledge base queries
2. **MCP tools** (when using `app_mcp.py`) - External data sources and documentation

To add new agents:
1. Create class inheriting from `BaseAgent`
2. Add tool in `OrchestratorAgent._setup_tools()`
3. Create corresponding prompt file in `prompts/`

To add new MCP servers:
1. Register in `core/mcp_manager.py` via `mcp_manager.register_server()`
2. Or add to `.mcp.json` configuration file
3. Restart bot with `python app_mcp.py`

### RAG Implementation

**Vector Store** (`core/vector_store.py`):
- Singleton pattern: `vector_store_manager` instantiated at module level
- Embeddings: OpenAI `text-embedding-3-small` (1536 dimensions)
- Backend: Supabase with pgvector extension
- Search function: `match_documents` (PostgreSQL stored procedure)

**Search Flow**:
```
User Query → RAGAgent.search_knowledge_base()
           → VectorStoreManager.search_with_score()
           → Supabase match_documents() with cosine similarity
           → Returns top-k documents with scores
           → Relevance banding: High (≥0.6), Medium (≥0.4), Low (<0.4)
```

**Known Issue**: Encoding mismatch in stored documents (Windows-1251 vs UTF-8) causing garbled Russian text. Workaround: similarity threshold lowered to 0.35 instead of typical 0.7+. See `SUPABASE_SETUP_NOTES.md` for details.

### Database Schema

Expected Supabase schema (see `NEXT_STEPS.md` for full SQL):
```sql
CREATE TABLE documents (
  id bigserial primary key,
  content text,
  metadata jsonb,
  embedding vector(1536)
);

CREATE FUNCTION match_documents(
  query_embedding vector(1536),
  match_threshold float,
  match_count int
) RETURNS TABLE (id bigint, content text, metadata jsonb, similarity float);
```

**Graceful Degradation**: System checks `vector_store_manager.is_available()` before operations. If Supabase unavailable, orchestrator handles all queries directly.

### Message Flow (End-to-End)

```
CLI Input → app.py REPL
         → OrchestratorAgent.process_message()
         → AgentExecutor.invoke()
         → [LangChain decides: direct answer OR knowledge_search tool]
         → [If tool called] RAGAgent.answer_question()
                          → Vector search with scoring
                          → Format context + prompt
                          → LLM generates answer
         → Return final response
         → Display in CLI
```

### Configuration System

**Pattern**: Pydantic `BaseSettings` in `core/config.py`
- Loads from environment variables and `.env` file (UTF-8)
- Global singleton: `from core.config import settings`
- Validates required fields and checks for placeholder values

**Key Fields**:
- `openai_api_key` - Required
- `supabase_url`, `supabase_key` - Optional (graceful fallback)
- `debug`, `log_level`, `environment` - Development settings

**Logging**: Configured via loguru in `app.py`
- File: `logs/app.log` (10MB rotation, 7 days retention)
- Structured JSON-like output with colors

## Code Patterns

### Prompt Externalization
All agent system prompts stored as Markdown in `prompts/`:
- `orchestrator.md` - Routing logic and tool usage instructions
- `rag_agent.md` - RAG behavior and answer formatting rules

Agents load via `_get_default_prompt()` with hardcoded fallbacks. Modify prompts without changing code.

### Singleton Pattern
- `vector_store_manager` - Single Supabase connection
- `settings` - Single config instance
- Import pre-instantiated objects, don't create new instances

### Error Handling
- All user-facing errors in Russian
- Graceful degradation (vector store optional)
- Logging with context (agent name, query, errors)

## Current Limitations

### Not Yet Implemented
- **Platform handlers**: No Telegram/Discord integration despite README claims (only CLI exists)
- **Conversation memory**: Each message is stateless, no history tracking
- **User profiles**: No `users` or `conversations` tables in database
- **Tool ecosystem**: `tools/` directory contains only empty placeholder files
- **Tests**: Test files are empty shells

### Technical Debt
- Encoding issues in Supabase documents (garbled Russian text)
- Similarity threshold workaround (0.35 instead of proper 0.7+)
- Hardcoded configuration: agent models, embedding model, thresholds
- Empty modules: `core/memory.py`, `schemas/models.py`, `tools/*.py`

### Architectural Constraints
- Single RAG agent hardcoded in orchestrator (not truly multi-agent yet)
- No dynamic agent registration mechanism
- Model selection not configurable (hardcoded to `gpt-4o-mini`)

## Project Structure Notes

```
Eneca_AI_bot/
├── agents/          # Agent implementations (BaseAgent, OrchestratorAgent, RAGAgent)
├── core/            # Singleton managers (config, vector_store, memory*)
├── prompts/         # Markdown system prompts for agents
├── schemas/         # Empty - intended for Pydantic models
├── tools/           # Empty - intended for LangChain tools
├── scripts/         # Empty - intended for data ingestion
├── logs/            # Rotated log files (gitignored)
├── app.py           # CLI entry point
└── test_bot.py      # Orchestrator routing tests
```

*Empty or partially implemented

## Important Files

- `agents/orchestrator.py:43` - Tool registration for routing
- `agents/rag_agent.py:45` - Vector search with relevance scoring
- `core/vector_store.py:23` - Supabase pgvector integration
- `core/config.py` - Environment-driven configuration
- `core/mcp_manager.py` - MCP servers management and integration
- `app_mcp.py` - Async CLI with MCP support
- `prompts/orchestrator.md` - Routing decision logic (Russian)
- `prompts/rag_agent.md` - RAG answer formatting rules (Russian)
- `docs/MCP_INTEGRATION.md` - MCP setup and usage guide
- `SUPABASE_SETUP_NOTES.md` - Known encoding issues and workarounds
- `NEXT_STEPS.md` - Planned features and Telegram handler example

## Language Conventions

- All code comments and docstrings: English
- All prompts, user messages, and errors: Russian
- Configuration keys and logs: English
