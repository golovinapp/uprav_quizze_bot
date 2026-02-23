"""
Main entry point — runs Telegram bot and web dashboard concurrently.

Usage:
    python main.py
"""

import asyncio
import logging

from aiohttp import web

import database as db
from config import WEB_HOST, WEB_PORT
from bot.handlers import dp, bot, set_bot_commands
from web.app import create_web_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup():
    logger.info("Initialising database…")
    await db.init_db()
    await set_bot_commands()
    logger.info("Database ready, bot commands set.")


async def on_shutdown():
    logger.info("Shutting down…")
    await bot.session.close()
    await db.close_db()


async def main():
    await on_startup()

    # Prepare web app
    web_app = create_web_app()
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, WEB_PORT)
    await site.start()
    logger.info(f"Web dashboard running at http://{WEB_HOST}:{WEB_PORT}")

    # Start bot polling
    try:
        logger.info("Starting bot polling…")
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
