import sys
import uvicorn
from fastapi import FastAPI, HTTPException
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

# --- Модели данных (Что мы принимаем от приложения) ---
class ChatRequest(BaseModel):
    message: str
    thread_id: str  # ID пользователя или чата, чтобы у каждого была своя память

class ChatResponse(BaseModel):
    response: str

# --- Глобальные переменные ---
agent = None

# --- Жизненный цикл (Запуск и остановка) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Эта часть срабатывает при запуске сервера
    setup_logging()
    logger.info("Starting Eneca AI API Server")
    
    global agent
    try:
        agent = OrchestratorAgent()
        logger.info("Orchestrator Agent initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize Agent: {e}")
        raise e
        
    yield  # Тут сервер работает
    
    # Эта часть срабатывает при выключении
    logger.info("Shutting down API Server")

# --- Инициализация приложения ---
app = FastAPI(title="Eneca AI Bot API", lifespan=lifespan)

# --- Эндпоинт (Ручка), в которую будет стучаться твое приложение ---
@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """
    Принимает JSON: {"message": "Привет", "thread_id": "user123"}
    Возвращает JSON: {"response": "Ответ бота"}
    """
    global agent
    
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")

    try:
        logger.info(f"Processing message for thread {request.thread_id}")
        
        # Вызываем твоего агента
        # Fastapi автоматически запустит это в отдельном потоке, чтобы не блокировать сервер
        bot_response = agent.process_message(
            request.message, 
            thread_id=request.thread_id
        )
        
        return ChatResponse(response=bot_response)

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Точка входа ---
if __name__ == "__main__":
    # Запускаем сервер на всех сетевых интерфейсах (0.0.0.0) на порту 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)