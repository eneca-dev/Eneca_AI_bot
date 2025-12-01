"""
CLI интерфейс для общения с Eneca AI Bot
Запуск: python chat_cli.py

Автоматически удаляет переопределение SIMILARITY_THRESHOLD из окружения
для корректной работы RAG с настройками из .env файла.
"""
import sys
import os

# CRITICAL: Remove SIMILARITY_THRESHOLD override BEFORE importing settings
if 'SIMILARITY_THRESHOLD' in os.environ:
    print(f"⚠️  Обнаружена переменная SIMILARITY_THRESHOLD={os.environ['SIMILARITY_THRESHOLD']} в окружении")
    print("   Удаляю её для использования значения из .env...\n")
    del os.environ['SIMILARITY_THRESHOLD']

from loguru import logger
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

def main():
    setup_logging()
    logger.info("Starting Eneca AI Bot CLI")

    # Показать конфигурацию
    print(f"{'='*60}")
    print(f"📊 КОНФИГУРАЦИЯ:")
    print(f"{'='*60}")
    print(f"SIMILARITY_THRESHOLD: {settings.similarity_threshold}")
    print(f"RAG enabled: {settings.supabase_rag_url is not None}")
    print(f"Memory enabled: {settings.enable_conversation_memory}")
    print(f"{'='*60}\n")

    # Инициализация агента
    try:
        agent = OrchestratorAgent()
        logger.info("Orchestrator Agent initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize Agent: {e}")
        return

    # Приветствие
    print("\n" + "="*60)
    print("🤖 ENECA AI BOT - CLI Interface")
    print("="*60)
    print("Введите ваш вопрос или команду:")
    print("  - 'exit' или 'quit' - выход")
    print("  - 'clear' - очистить экран")
    print("="*60 + "\n")

    # REPL цикл
    thread_id = "cli_user"
    message_count = 0

    while True:
        try:
            # Получить ввод от пользователя
            user_input = input("\n👤 Вы: ").strip()

            # Обработка команд
            if user_input.lower() in ['exit', 'quit', 'выход']:
                print("\n👋 До свидания!")
                break

            if user_input.lower() == 'clear':
                import os
                os.system('cls' if os.name == 'nt' else 'clear')
                continue

            if not user_input:
                continue

            # Обработка сообщения
            message_count += 1
            logger.info(f"Processing message #{message_count}: {user_input[:50]}...")

            try:
                response = agent.process_message(
                    user_message=user_input,
                    thread_id=thread_id
                )

                print(f"\n🤖 Бот: {response}")
                logger.info(f"Response sent for message #{message_count}")

            except Exception as e:
                logger.error(f"Error processing message: {e}")
                print(f"\n❌ Ошибка: {e}")

        except KeyboardInterrupt:
            print("\n\n👋 До свидания!")
            break
        except EOFError:
            print("\n\n👋 До свидания!")
            break

if __name__ == "__main__":
    main()
