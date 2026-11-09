"""Entry point: python -m app.run_bot"""
from __future__ import annotations

import asyncio
import logging
import signal

from app.bot.client import RedditBridgeBot
from app.config.logging import configure_logging
from app.config.settings import get_settings
from app.database.session import create_session_factory, init_db
from app.reddit.client import RedditClient


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine, sessionmaker = create_session_factory(settings.database_url.get_secret_value())
    await init_db(engine)
    reddit = RedditClient(settings.reddit_client_id, settings.reddit_client_secret.get_secret_value(),
                          settings.reddit_user_agent)
    bot = RedditBridgeBot(settings, sessionmaker, reddit)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):  # graceful shutdown
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.close()))
        except NotImplementedError:  # Windows
            pass
    try:
        await bot.start(settings.discord_bot_token.get_secret_value())
    finally:
        await engine.dispose()
        logging.getLogger(__name__).info("stopped")


if __name__ == "__main__":
    asyncio.run(main())
