# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Eneca AI Bot is a RAG-enabled chatbot built with LangChain, LangGraph, Supabase (pgvector), and Python. It features a dynamic agent registry system with an orchestrator that routes queries to specialized agents. The system supports conversation memory via SQLite checkpointing and can be deployed via Docker/Nginx. All prompts and user-facing messages are in Russian.

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
# CLI interface with conversation memory
python app.py

# FastAPI webhook server (for external integrations)
python server.py

# Test scripts
python tests/test_bot.py            # Test orchestrator routing
python scripts/debug_supabase.py    # Debug Supabase vector search
```

### Docker Deployment
```bash
# Build and run with Docker Compose (includes Nginx reverse proxy)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Configuration

Copy `.env.example` to `.env` and configure:
- `OPENAI_API_KEY` - Required for LLM and embeddings
- `SUPABASE_URL` and `SUPABASE_KEY` - Optional, bot runs without vector store
- `ENABLE_CONVERSATION_MEMORY` - Enable/disable conversation memory (default: true)
- `MEMORY_TYPE` - Memory backend: `memory` (in-memory) or `sqlite` (persistent)
- `MEMORY_DB_PATH` - SQLite database path for conversation history
- `LOG_LEVEL` - Logging level (default: INFO)

## Architecture

### Dynamic Agent System

The system implements a **plugin-based agent architecture** with dynamic registration:

1. **BaseAgent** ([agents/base.py](agents/base.py)) - Abstract base class providing:
   - LangChain ChatOpenAI initialization (model, temperature)
   - System prompt loading from markdown files in `prompts/`
   - Common `invoke()` method for LLM calls

2. **AgentRegistry** ([core/agent_registry.py](core/agent_registry.py)) - Dynamic agent management:
   - Loads agent configurations from [config/agents.yaml](config/agents.yaml)
   - Automatically creates LangChain tools from registered agents
   - Supports priority-based agent registration
   - Lazy instantiation of agent instances
   - Enable/disable agents without code changes

3. **OrchestratorAgent** ([agents/orchestrator.py](agents/orchestrator.py):79) - Main entry point:
   - Uses LangGraph's `create_react_agent` (ReAct pattern)
   - Routes queries to appropriate agents via LLM tool selection
   - Supports conversation memory with thread-based context
   - System prompt: [prompts/orchestrator.md](prompts/orchestrator.md)

4. **MCPAgent** ([agents/mcp_agent.py](agents/mcp_agent.py)) - Project management specialist:
   - Connects to external MCP server via JSON-RPC 2.0
   - Manages 21 tools for projects, stages, objects, sections, employees
   - Temperature: 0.3 (lower for precise tool selection)
   - LLM-based query parsing for tool + arguments extraction
   - System prompt: [prompts/mcp_agent.md](prompts/mcp_agent.md)

5. **RAGAgent** ([agents/rag_agent.py](agents/rag_agent.py):45) - Knowledge base specialist:
   - Performs vector similarity search via Supabase pgvector
   - Temperature: 0.3 (lower for factual responses)
   - Strict policy: answers ONLY from retrieved documents
   - System prompt: [prompts/rag_agent.md](prompts/rag_agent.md)

6. **MemoryManager** ([core/memory.py](core/memory.py)) - Conversation persistence:
   - Supports InMemorySaver (non-persistent) and SqliteSaver (persistent)
   - Thread-based conversation tracking
   - Graceful fallback if memory disabled

### Routing Mechanism

The orchestrator uses **LangGraph ReAct agent** with automatic tool selection:
- Tools auto-generated from [config/agents.yaml](config/agents.yaml) via [core/agent_registry.py](core/agent_registry.py):214
- LLM analyzes query and selects appropriate tool via function calling
- Tool invocation → specialized agent → formatted response → orchestrator finalizes
- All tool descriptions in Russian for optimal routing accuracy

**Current Tools:**
- `mcp_tools` - MCP agent for project/employee operations (priority: 20)
- `knowledge_search` - RAG agent for knowledge base queries (priority: 10)

**Adding New Agents:**
1. Create agent class inheriting from `BaseAgent` in [agents/](agents/)
2. Add entry to [config/agents.yaml](config/agents.yaml) with:
   - `name` - Tool name for orchestrator
   - `class_path` - Full Python import path (e.g., `agents.rag_agent.RAGAgent`)
   - `enabled` - Enable/disable without code changes
   - `priority` - Higher numbers loaded first
   - `tool_description` - Russian description for LLM routing
   - `config` - Agent-specific parameters
3. Create system prompt file in [prompts/](prompts/)
4. Restart bot - agent auto-registers via `agent_registry.load_from_yaml()`

**Agent Requirements:**
- Must inherit from `BaseAgent`
- Implement `answer_question(query: str)` or `process_message(user_message: str)` method
- Return string response

### MCP Implementation

**MCP Agent** ([agents/mcp_agent.py](agents/mcp_agent.py)):
- HTTP client with 30-second timeout for JSON-RPC 2.0 calls
- MCP server URL: `https://eneca-mcp-server-2c6301361601.herokuapp.com/mcp`
- Dynamic tool loading via `tools/list` JSON-RPC method
- 21 available tools: projects, stages, objects, sections, employees management

**MCP Flow**:
```
User Query → OrchestratorAgent.process_message()
           → LangGraph ReAct agent selects mcp_tools
           → MCPAgent.process_message()
           → LLM parses query → extracts tool name + arguments
           → HTTP POST to MCP server (JSON-RPC 2.0)
           → MCP server returns result
           → MCPAgent formats response in Russian
           → Returns answer to orchestrator
```

**Available MCP Tools:**
- **Projects**: create_project, search_projects, get_project_details, update_project, get_project_team
- **Stages**: create_stage, search_stages, update_stage
- **Objects**: create_object, search_objects, update_object
- **Sections**: create_section, search_sections, update_section
- **Employees**: search_employee_full_info, search_by_responsible, search_users, get_employee_workload
- **Reports**: generate_project_report_plan_fact

**Error Handling:**
- Timeout after 30 seconds with user-friendly message
- JSON-RPC errors extracted and displayed in Russian
- Graceful fallback if MCP server unavailable

### RAG Implementation

**Vector Store** ([core/vector_store.py](core/vector_store.py)):
- Singleton pattern: `vector_store_manager` instantiated at module level
- Embeddings: OpenAI `text-embedding-3-small` (1536 dimensions)
- Backend: Supabase with pgvector extension
- Search function: `match_documents` (PostgreSQL stored procedure)

**Search Flow**:
```
User Query → OrchestratorAgent.process_message()
           → LangGraph ReAct agent selects knowledge_search tool
           → RAGAgent.answer_question()
           → VectorStoreManager.search_with_score()
           → Supabase match_documents() with cosine similarity
           → Returns top-k documents with scores
           → Relevance banding: High (≥0.8), Medium (≥0.6), Low (<0.6)
           → RAGAgent formats context + calls LLM
           → Returns answer to orchestrator
```

**Encoding Issue Resolution**: Documents with encoding issues can be fixed using the migration script:
- Run `python scripts/fix_encoding_migration.py` for analysis (dry-run)
- Run with `--execute` flag to perform migration with automatic backup
- Automatic UTF-8 validation on all new document uploads
- See [docs/ENCODING_MIGRATION_GUIDE.md](docs/ENCODING_MIGRATION_GUIDE.md) for full guide
- After migration, similarity threshold is 0.7 for high-quality matches

### Conversation Memory

**Memory Architecture** ([core/memory.py](core/memory.py)):
- Thread-based conversation tracking via LangGraph checkpointers
- Each conversation has unique `thread_id` for context isolation
- Orchestrator passes `thread_id` in config: `{"configurable": {"thread_id": "user123"}}`

**Storage Backends:**
1. **InMemorySaver** - Fast, non-persistent (lost on restart)
2. **SqliteSaver** - Persistent to disk, survives restarts
3. **PostgreSQL/Redis** - Planned but not implemented

**Usage in Code:**
```python
# Process message with conversation context
orchestrator.process_message(
    user_message="Привет!",
    thread_id="user123"  # Maintains conversation history for this user
)
```

**Configuration:** Set `ENABLE_CONVERSATION_MEMORY=true` and `MEMORY_TYPE=sqlite` in `.env`

### Database Schema

Expected Supabase schema (see [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) for full SQL):
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

**Graceful Degradation**: System checks `vector_store_manager.is_available()` before operations. If Supabase unavailable, orchestrator handles all queries directly without RAG.

### Message Flow (End-to-End)

**CLI Interface** ([app.py](app.py)):
```
User Input → app.py REPL
          → OrchestratorAgent.process_message(message, thread_id)
          → LangGraph ReAct agent.invoke()
          → [ReAct Loop]:
               1. LLM analyzes query
               2. Decides: direct answer OR call tool
               3. If tool: knowledge_search → RAGAgent
                    → Vector search + context formatting
                    → LLM generates answer from context
               4. Return to orchestrator
               5. Final response formatting
          → Memory checkpoint saved (if enabled)
          → Display in CLI
```

**Webhook Interface** ([server.py](server.py)):
```
HTTP POST /webhook → FastAPI endpoint
                  → Extract message + user_id
                  → OrchestratorAgent.process_message(message, thread_id=user_id)
                  → [Same ReAct flow as above]
                  → Memory checkpoint saved
                  → Return JSON response
```

### Configuration System

**Pattern**: Pydantic `BaseSettings` in [core/config.py](core/config.py)
- Loads from environment variables and `.env` file (UTF-8)
- Global singleton: `from core.config import settings`
- Validates required fields and checks for placeholder values

**Key Configuration Fields**:
- `openai_api_key` - Required for LLM/embeddings
- `supabase_url`, `supabase_key` - Optional (graceful fallback)
- `orchestrator_model`, `orchestrator_temperature` - Orchestrator LLM config
- `rag_agent_model`, `rag_agent_temperature` - RAG agent LLM config
- `enable_conversation_memory` - Toggle memory system
- `memory_type` - Backend: `memory` or `sqlite`
- `memory_db_path` - SQLite database location
- `debug`, `log_level`, `environment` - Development settings

**Agent Configuration**: [config/agents.yaml](config/agents.yaml)
- YAML-based agent registration
- No code changes needed to add/remove agents
- Priority-based tool ordering

**Logging**: Configured via loguru in [app.py](app.py)
- File: `logs/app.log` (10MB rotation, 7 days retention)
- Structured JSON-like output with colors

## Code Patterns

### Prompt Externalization
All agent system prompts stored as Markdown in [prompts/](prompts/):
- [orchestrator.md](prompts/orchestrator.md) - Routing logic and tool usage instructions
- [rag_agent.md](prompts/rag_agent.md) - RAG behavior and answer formatting rules

Agents load via `_get_default_prompt()` with hardcoded fallbacks. Modify prompts without changing code.

### Singleton Pattern
Critical singletons instantiated at module level:
- `vector_store_manager` ([core/vector_store.py](core/vector_store.py)) - Single Supabase connection
- `memory_manager` ([core/memory.py](core/memory.py)) - Single checkpointer instance
- `agent_registry` ([core/agent_registry.py](core/agent_registry.py)) - Single agent registry
- `settings` ([core/config.py](core/config.py)) - Single config instance

**IMPORTANT**: Always import these pre-instantiated objects, never create new instances.

### Agent Registration Pattern
Dynamic agent loading via YAML configuration:
1. Define agent in [config/agents.yaml](config/agents.yaml)
2. AgentRegistry loads configuration at startup
3. Orchestrator auto-creates tools via `agent_registry.create_tools_for_agents()`
4. Tools dynamically invoke agents via lazy instantiation

### Error Handling
- All user-facing errors in Russian
- Graceful degradation (vector store optional, memory optional)
- Logging with context (agent name, query, errors)
- Try/except blocks return user-friendly error messages

## Current Limitations

### Not Yet Implemented
- **Platform handlers**: No Telegram/Discord bot integration (only CLI + webhook server)
- **User profiles**: No `users` or `conversations` tables in database
- **Advanced memory**: PostgreSQL/Redis checkpointers not implemented
- **Tests**: Test files exist but coverage is minimal

### Technical Debt
- Encoding issues in Supabase documents (garbled Russian text)
- Similarity threshold workaround (0.35 instead of proper 0.7+)
- Empty placeholder directories: `schemas/`, some `scripts/`

### Architecture Notes
- Memory system is thread-based, not user-based (no built-in user authentication)
- Webhook server exists ([server.py](server.py)) but no platform-specific handlers
- Agent registry loads all enabled agents at startup (no hot-reloading)

## Project Structure

```
Eneca_AI_bot/
├── agents/           # Agent implementations
│   ├── base.py       # Abstract BaseAgent class
│   ├── orchestrator.py  # Main routing agent with LangGraph ReAct
│   └── rag_agent.py  # RAG knowledge base agent
├── core/             # Core singleton managers
│   ├── config.py     # Pydantic settings from .env
│   ├── vector_store.py  # Supabase pgvector integration
│   ├── memory.py     # LangGraph checkpointer management
│   └── agent_registry.py  # Dynamic agent loading from YAML
├── config/           # Configuration files
│   └── agents.yaml   # Agent definitions and tool descriptions
├── prompts/          # Markdown system prompts (external from code)
│   ├── orchestrator.md  # Orchestrator routing instructions
│   └── rag_agent.md     # RAG answer formatting rules
├── docs/             # Documentation
├── scripts/          # Utility scripts (debug_supabase.py, etc.)
├── tests/            # Test files
├── logs/             # Rotated log files (gitignored)
├── data/             # Conversation memory SQLite databases
├── app.py            # CLI entry point with REPL
├── server.py         # FastAPI webhook server
├── docker-compose.yml  # Docker deployment with Nginx
└── requirements.txt  # Python dependencies
```

## Key Files Reference

**Core Architecture:**
- [agents/base.py](agents/base.py) - Abstract agent base class
- [agents/orchestrator.py](agents/orchestrator.py):79 - Main routing logic with LangGraph
- [agents/mcp_agent.py](agents/mcp_agent.py) - MCP server integration via JSON-RPC 2.0
- [agents/rag_agent.py](agents/rag_agent.py):45 - Vector search and RAG pipeline
- [core/agent_registry.py](core/agent_registry.py):214 - Dynamic agent/tool creation
- [core/memory.py](core/memory.py) - Conversation checkpointing
- [core/vector_store.py](core/vector_store.py) - Supabase pgvector integration
- [core/config.py](core/config.py) - Pydantic settings management

**Configuration:**
- [config/agents.yaml](config/agents.yaml) - Agent registry configuration
- [.env](.env) - Environment variables (API keys, database URLs)

**Entry Points:**
- [app.py](app.py) - CLI interface with REPL
- [server.py](server.py) - FastAPI webhook server

**Prompts (Russian):**
- [prompts/orchestrator.md](prompts/orchestrator.md) - Routing and tool selection logic
- [prompts/mcp_agent.md](prompts/mcp_agent.md) - MCP tool selection and formatting
- [prompts/rag_agent.md](prompts/rag_agent.md) - RAG answer formatting rules

**Documentation:**
- [docs/SUPABASE_SETUP_NOTES.md](docs/SUPABASE_SETUP_NOTES.md) - Encoding issues and workarounds
- [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) - Planned features

## Language Conventions

- All code comments and docstrings: English
- All prompts, user messages, and errors: Russian
- Configuration keys and logs: English
