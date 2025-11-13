"""
Main entry point for Eneca AI Bot.
"""

import asyncio
from loguru import logger
from config import settings


def setup_logging():
    """Configure logging for the application."""
    logger.remove()  # Remove default handler
    logger.add(
        "logs/bot_{time}.log",
        rotation="1 day",
        retention="7 days",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )
    logger.add(
        lambda msg: print(msg, end=""),
        level=settings.log_level,
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
    )


async def main():
    """Main application entry point."""
    setup_logging()

    logger.info("Starting Eneca AI Bot...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Platform: {settings.bot_platform}")
    logger.info(f"Debug mode: {settings.debug}")

    try:
        # TODO: Initialize bot based on platform
        if settings.bot_platform == "telegram":
            logger.info("Initializing Telegram bot...")
            # from bot import TelegramBot
            # bot = TelegramBot()
            # await bot.run()
        elif settings.bot_platform == "discord":
            logger.info("Initializing Discord bot...")
            # from bot import DiscordBot
            # bot = DiscordBot()
            # await bot.run()
        else:
            logger.error(f"Unsupported platform: {settings.bot_platform}")
            return

        logger.info("Bot initialization complete. TODO: Implement bot logic.")

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Fatal error occurred: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
