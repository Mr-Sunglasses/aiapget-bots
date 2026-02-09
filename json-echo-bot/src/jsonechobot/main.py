import html
import json
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes, MessageHandler, filters

load_dotenv()

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger("jsonechobot")

# Telegram message length limit
MAX_MESSAGE_LENGTH = 4096
# Overhead for the <pre> wrapper + part label (generous estimate)
CODE_WRAPPER_OVERHEAD = 40


def _wrap_code(text: str, part_label: str = "") -> str:
    """Wrap text in an HTML <pre> code block, escaping HTML entities."""
    escaped = html.escape(text)
    if part_label:
        return f"<b>{html.escape(part_label)}</b>\n<pre>{escaped}</pre>"
    return f"<pre>{escaped}</pre>"


async def _echo_json(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with the full update payload as pretty-printed JSON in a code block."""
    payload = update.to_dict()
    raw_json = json.dumps(payload, ensure_ascii=False, indent=2)

    usable_limit = MAX_MESSAGE_LENGTH - CODE_WRAPPER_OVERHEAD

    if len(raw_json) <= usable_limit:
        await update.message.reply_text(
            _wrap_code(raw_json),
            parse_mode=ParseMode.HTML,
        )
    else:
        # Split on line boundaries to stay under the limit
        chunks: list[str] = []
        current = ""
        for line in raw_json.splitlines(keepends=True):
            if len(current) + len(line) > usable_limit:
                chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)

        for i, chunk in enumerate(chunks, 1):
            await update.message.reply_text(
                _wrap_code(chunk, part_label=f"[Part {i}/{len(chunks)}]"),
                parse_mode=ParseMode.HTML,
            )


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    application = Application.builder().token(token).build()

    # Catch every message (including forwarded ones, polls, etc.)
    application.add_handler(
        MessageHandler(filters.ALL, _echo_json)
    )

    LOGGER.info("JSON Echo Bot started — send any message to get its update JSON.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
