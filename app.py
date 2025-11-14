import sys
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

    # Initialize orchestrator agent
    agent = OrchestratorAgent()

    print("\n" + "=" * 60)
    print("> Eneca AI Bot - CLI Mode")
    print("=" * 60)
    print("Type your message and press Enter to chat")
    print("Type 'exit' or 'quit' to stop\n")

    while True:
        try:
            # Get user input
            user_input = input("You: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("\n=K Goodbye!")
                break

            # Process message through orchestrator
            response = agent.process_message(user_input)

            print(f"\n> Bot: {response}\n")

        except KeyboardInterrupt:
            print("\n\n=K Goodbye!")
            break
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            print(f"\nL Error: {e}\n")


if __name__ == "__main__":
    main()
