"""Interactive MCP test - try different queries"""
from agents.orchestrator import OrchestratorAgent
from loguru import logger
import sys

logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>")

def main():
    print("\n" + "="*60)
    print("🤖 Eneca AI Bot - Local MCP Test")
    print("="*60)

    orchestrator = OrchestratorAgent()

    print("\n✅ Bot initialized successfully")
    print("📝 Try these queries:")
    print("   - Покажи все проекты")
    print("   - Найди сотрудника Иванов")
    print("   - Команда проекта Башня")
    print("   - exit (to quit)\n")

    thread_id = "test_session"

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'выход']:
                print("\n👋 Goodbye!")
                break

            print("\n🤔 Processing...\n")
            response = orchestrator.process_message(user_input, thread_id=thread_id)
            print(f"Bot: {response}\n")
            print("-" * 60 + "\n")

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
