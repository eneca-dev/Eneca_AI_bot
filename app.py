import sys
import uvicorn
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger
from contextlib import asynccontextmanager

# Импорты агента и базы данных
from agents.orchestrator import OrchestratorAgent
from agents.analytics_agent import AnalyticsAgent
from agents.analytics_models import AnalyticsResult
from core.config import settings
from database.supabase_client import supabase_db_client

# --- Настройка Логирования ---
def setup_logging():
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=settings.log_level
    )
    logger.add("logs/app.log", rotation="10 MB", retention="7 days", level=settings.log_level)

# --- Модели данных ---
class ChatRequest(BaseModel):
    message: str
    thread_id: str

class ChatResponse(BaseModel):
    response: str

class AnalyticsRequest(BaseModel):
    """Analytics request model"""
    query: str
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class AnalyticsResponse(BaseModel):
    """Analytics response model"""
    type: str  # "text", "table", "chart", "mixed"
    content: Any  # String, list, or dict depending on type
    sql_query: Optional[str] = None
    chart_config: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = {}
    success: bool = True
    error: Optional[str] = None

# --- Модели для Supabase Webhook ---
class SupabaseWebhookRecord(BaseModel):
    """Single record from Supabase webhook payload"""
    id: str
    user_id: str
    thread_id: str
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None

class SupabaseWebhookPayload(BaseModel):
    """Full webhook payload from Supabase"""
    type: str  # "INSERT", "UPDATE", "DELETE"
    table: str
    record: SupabaseWebhookRecord
    schema: str = "public"
    old_record: Optional[Dict] = None

class WebhookResponse(BaseModel):
    """Immediate response to webhook"""
    status: str
    message_id: Optional[str] = None

# --- Глобальные переменные ---
agent = None
analytics_agent = None
realtime_listener = None  # Realtime subscription listener

# --- Жизненный цикл ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting Eneca AI API Server")

    global agent
    try:
        agent = OrchestratorAgent()
        logger.info("Orchestrator Agent initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize Agent: {e}")
        raise e

    # Start Realtime listener
    global realtime_listener
    try:
        from core.realtime_listener import RealtimeListener
        realtime_listener = RealtimeListener(agent)
        realtime_listener.start()
        logger.info("✅ Realtime listener started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start Realtime listener: {e}")
        # Don't crash - webhook endpoint exists as fallback

    yield

    # Stop Realtime listener on shutdown
    if realtime_listener:
        realtime_listener.stop()

    logger.info("Shutting down API Server")

# --- Инициализация приложения ---
app = FastAPI(title="Eneca AI Bot API", lifespan=lifespan)

# ==========================================
# 🔥 НАСТРОЙКА CORS (ДОСТУП ДЛЯ ENECA.WORK)
# ==========================================
origins = [
    "https://eneca.work",          # Ваш основной сайт
    "https://www.eneca.work",      # С www
    "http://localhost:3000",       # Для локальной разработки фронтенда
    "http://localhost:8080",
    "https://ai-bot.eneca.work"    # Сам бот
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,         # Разрешаем запросы только с этих сайтов
    allow_credentials=True,
    allow_methods=["*"],           # Разрешаем любые методы (POST, GET, OPTIONS)
    allow_headers=["*"],           # Разрешаем любые заголовки
)
# ==========================================

# --- Эндпоинт ---
def get_analytics_agent() -> AnalyticsAgent:
    """Get or create analytics agent instance"""
    global analytics_agent
    if analytics_agent is None:
        logger.info("Initializing AnalyticsAgent...")
        analytics_agent = AnalyticsAgent()
        logger.info("AnalyticsAgent initialized successfully")
    return analytics_agent

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    global agent

    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    try:
        logger.info(f"Processing message for thread {request.thread_id}")

        # Запускаем обработку сообщения
        bot_response = agent.process_message(
            request.message,
            thread_id=request.thread_id
        )

        return ChatResponse(response=bot_response)

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analytics", response_model=AnalyticsResponse)
async def analytics_endpoint(request: AnalyticsRequest):
    """
    Analytics endpoint for data analysis, reporting, and visualization

    Expected payload:
    {
        "query": "Natural language query for analytics",
        "user_id": "optional-user-id",
        "user_role": "optional-user-role (admin/manager/engineer/viewer/guest)",
        "metadata": {}
    }
    """
    try:
        logger.info(f"📊 Received analytics request: query='{request.query}', user_id={request.user_id}")

        # Get analytics agent
        agent_instance = get_analytics_agent()

        # Determine user role and ID for RBAC
        user_role = request.user_role
        user_id = request.user_id  # Extract user_id from request

        if not user_role and user_id:
            # Load user role from database
            if supabase_db_client.is_available():
                user_context = supabase_db_client.get_user_profile(user_id)
                if user_context:
                    user_role = user_context.get('role_name', 'guest')
                    logger.info(f"Loaded user role from DB: {user_role}")
                else:
                    user_role = 'guest'
                    logger.warning(f"No profile found for user_id={user_id}, using guest role")
            else:
                user_role = 'guest'
                logger.warning("Supabase not available, using guest role")
        elif not user_role:
            user_role = 'guest'
            user_id = None  # No user_id if no role provided
            logger.info("No user_role or user_id provided, using guest role")

        # Process analytics query with user_id for personalized queries
        logger.info(f"Processing analytics query with role: {user_role}, user_id: {user_id}")
        result: AnalyticsResult = agent_instance.process_analytics(
            user_query=request.query,
            user_role=user_role,
            user_id=user_id  # Pass user_id to agent
        )

        logger.info(f"Analytics result generated: type={result.type}, rows={result.metadata.get('row_count', 0)}")

        # Create response
        response = AnalyticsResponse(
            type=result.type,
            content=result.content,
            sql_query=result.sql_query,
            chart_config=result.chart_config,
            metadata=result.metadata,
            success=True
        )

        logger.info(f"Sending analytics response: type={response.type}, content_type={type(response.content)}")
        if response.type == "table":
            logger.info(f"Table content structure: {response.content}")

        return response

    except Exception as e:
        logger.error(f"Error processing analytics request: {e}", exc_info=True)
        return AnalyticsResponse(
            type="text",
            content="Произошла ошибка при обработке запроса на аналитику.",
            success=False,
            error=str(e)
        )

# --- Background Task Function ---
def process_webhook_message(record: SupabaseWebhookRecord):
    """
    Background task to process webhook message from Supabase

    This function runs AFTER we've sent 200 OK to Supabase.
    It calls the agent and writes the response back to the database.
    """
    thread_id = record.thread_id
    user_message = record.content
    user_id = record.user_id

    logger.info(f"Background processing started for thread: {thread_id}")

    try:
        # 1. Call agent to generate response
        bot_response = agent.process_message(
            user_message=user_message,
            thread_id=thread_id
        )

        logger.info(f"Agent generated response for thread: {thread_id} (length: {len(bot_response)})")

        # 2. Write response to Supabase
        if supabase_db_client.is_available():
            result = supabase_db_client.insert_message(
                conversation_id=thread_id,  # thread_id == conversation_id
                content=bot_response,
                user_id=user_id,
                role="assistant",
                metadata=record.metadata
            )

            if result:
                logger.success(f"Response written to database for thread: {thread_id}")
            else:
                logger.error(f"Failed to write response to database for thread: {thread_id}")
        else:
            logger.error("Supabase DB client not available - cannot write response")

    except Exception as e:
        logger.error(f"Background task failed for thread {thread_id}: {e}")

        # Optionally: Write error message to chat
        try:
            if supabase_db_client.is_available():
                supabase_db_client.insert_message(
                    conversation_id=thread_id,  # thread_id == conversation_id
                    content="Извините, произошла ошибка при обработке вашего сообщения. Пожалуйста, попробуйте еще раз.",
                    user_id=user_id,
                    role="assistant"
                )
        except:
            pass  # Silently fail if error message can't be written

# --- Webhook Endpoint ---
@app.post("/webhook")  
@app.post("/webhook/supabase", response_model=WebhookResponse)
async def supabase_webhook(
    payload: SupabaseWebhookPayload,
    background_tasks: BackgroundTasks
):
    """
    Supabase Database Webhook endpoint

    Receives notifications when new messages are inserted into chat_messages table.
    Immediately returns 200 OK, then processes message in background.

    CRITICAL: Only processes messages with role='user' to prevent infinite loop.
    """

    # CRITICAL: Prevent infinite loop - ignore bot's own messages
    if payload.record.role != "user":
        logger.info(f"Ignoring non-user message (role={payload.record.role})")
        return WebhookResponse(status="ignored")

    logger.info(f"Webhook received for thread: {payload.record.thread_id}")

    # Schedule background processing
    background_tasks.add_task(process_webhook_message, payload.record)

    # Immediate 200 OK response to Supabase
    return WebhookResponse(
        status="accepted",
        message_id=payload.record.id
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, timeout_keep_alive=300)