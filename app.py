import sys
import uuid
from loguru import logger
from agents.orchestrator import OrchestratorAgent
from core.config import settings


def setup_logging():
    """Configure logging"""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=settings.log_level
    )
    logger.add(
        "logs/app.log",
        rotation="10 MB",
        retention="7 days",
        level=settings.log_level
    )


def main():
    """Main CLI interface for testing the bot"""
    setup_logging()

    logger.info("Starting Eneca AI Bot (CLI mode)")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Conversation memory: {'enabled' if settings.enable_conversation_memory else 'disabled'}")

    # Initialize orchestrator agent
    agent = OrchestratorAgent()

    # Generate unique thread ID for this conversation session
    thread_id = str(uuid.uuid4())
    logger.info(f"Created conversation thread: {thread_id}")

    print("\n" + "=" * 60)
    print("> Eneca AI Bot - CLI Mode")
    print("=" * 60)
    print("Type your message and press Enter to chat")
    print("Type 'exit' or 'quit' to stop")
    if settings.enable_conversation_memory:
        print(f"Conversation memory: ENABLED (thread: {thread_id[:8]}...)")
    else:
        print("Conversation memory: DISABLED")
    print()

    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("\nGoodbye!")
                break

            # Process message through orchestrator with thread_id
            response = agent.process_message(user_input, thread_id=thread_id)

            print(f"\n> Bot: {response}\n")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            print(f"\nError: {e}\n")


if __name__ == "__main__":
    main()
