"""Main entry point for multi-exchange bot."""

import asyncio
import sys
from pathlib import Path
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.bot import MultiExchangeBot
from src.config import get_config


def setup_logging(config):
    """Setup logging configuration.

    Args:
        config: Bot configuration
    """
    log_level = config.log_level
    log_file = Path(__file__).parent / "bot.log"

    # Remove default handler
    logger.remove()

    # Add console handler
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True,
    )

    # Add file handler
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        level=log_level,
        rotation="100 MB",
        retention="7 days",
    )

    logger.info(f"Logging initialized (level: {log_level})")


async def main():
    """Main function."""
    # Load configuration
    config = get_config()

    # Setup logging
    setup_logging(config)

    logger.info("=" * 80)
    logger.info("Multi-Exchange Trading Bot")
    logger.info("=" * 80)
    logger.info(f"Mode: {config.mode}")
    logger.info(f"Enabled exchanges: {config.get_enabled_exchanges()}")

    if config.is_test_mode:
        logger.warning("Running in TEST mode - No real trades will be executed")
    else:
        logger.warning("Running in LIVE mode - Real trades will be executed!")
        # Add confirmation prompt for live mode
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            logger.info("Aborted by user")
            return

    # Create and run bot
    bot = MultiExchangeBot(config)

    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting...")
        sys.exit(0)
