"""Entrypoint for the BilingualBot Telegram bot."""

import logging
import os
import sys

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder

from bot.handlers import register_handlers

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN not set. Copy .env.example to .env and fill in your token.")
        sys.exit(1)

    app = ApplicationBuilder().token(token).build()
    register_handlers(app)

    logger.info("BilingualBot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
