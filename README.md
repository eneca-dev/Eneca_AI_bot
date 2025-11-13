# Eneca AI Bot

AI-powered bot built with LangChain, Supabase, and Python.

## Features

- Multi-platform support (Telegram, Discord)
- LangChain-based AI agents
- Supabase database integration
- Configurable LLM providers (OpenAI, Anthropic, Groq)
- Structured logging with Loguru

## Project Structure

```
Eneca_AI_bot/
├── agents/          # LangChain AI agents
├── database/        # Supabase integration
├── handlers/        # Message handlers
├── utils/           # Utility functions
├── config.py        # Configuration management
├── main.py          # Application entry point
├── requirements.txt # Python dependencies
└── .env.example     # Environment variables template
```

## Prerequisites

- Python 3.10 or higher
- Supabase account and project
- Bot token (Telegram/Discord)
- LLM API key (OpenAI, Anthropic, etc.)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd Eneca_AI_bot
```

2. Create and activate virtual environment:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/MacOS
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:
- `BOT_TOKEN`: Your bot token
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase anon/public key
- `OPENAI_API_KEY`: Your OpenAI API key (or other LLM provider)

## Supabase Setup

1. Create a new project at [supabase.com](https://supabase.com)
2. Copy your project URL and anon key to `.env`
3. Create necessary tables in your Supabase project:

```sql
-- Example table structure (customize as needed)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT UNIQUE NOT NULL,
    username TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    message TEXT NOT NULL,
    response TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Usage

Run the bot:
```bash
python main.py
```

## Development

### Adding New Agents

Create agent files in the `agents/` directory:

```python
# agents/my_agent.py
from langchain.agents import AgentExecutor
from langchain.tools import Tool

def create_my_agent():
    # Agent implementation
    pass
```

### Adding Database Models

Create database interaction files in the `database/` directory:

```python
# database/models.py
from supabase import Client
from config import settings

def get_supabase_client() -> Client:
    # Database client implementation
    pass
```

## Configuration

All configuration is managed through environment variables. See [.env.example](.env.example) for available options.

Key configuration options:
- `BOT_PLATFORM`: Platform to use (telegram/discord)
- `DEBUG`: Enable debug mode
- `LOG_LEVEL`: Logging level (INFO/DEBUG/WARNING/ERROR)
- `AGENT_MAX_ITERATIONS`: Maximum iterations for agents
- `LANGCHAIN_TRACING_V2`: Enable LangChain tracing

## Logging

Logs are stored in the `logs/` directory with daily rotation. The retention period is 7 days.

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

## Support

[Add support information here]
