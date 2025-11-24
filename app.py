import sys
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # <--- НОВЫЙ ИМПОРТ
from pydantic import BaseModel
from loguru import logger
from contextlib import asynccontextmanager

# Импорты твоего агента
from agents.orchestrator import OrchestratorAgent
from core.config import settings

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

# --- Глобальные переменные ---
agent = None

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
        
    yield
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)