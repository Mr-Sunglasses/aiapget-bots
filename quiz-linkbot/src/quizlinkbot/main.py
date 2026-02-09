"""
Quiz Link Extractor Bot
=======================
Telegram bot that collects forwarded @QuizBot messages, extracts quiz IDs
from the inline keyboard buttons, and sends back a .txt file with all links.

Flow:
  1. User sends /prepare  → bot enters "collecting" mode
  2. User forwards quiz messages → bot extracts quiz IDs from reply_markup
  3. User sends /finish   → bot sends a .txt file with all extracted quiz links
"""

import io
import logging
import os
import re

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger("quizlinkbot")

# Per-chat state: chat_id → ordered dict used as an ordered set (value ignored)
_sessions: dict[int, dict[str, None]] = {}
# Track which chats are in "collecting" mode
_active: set[int] = set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_quiz_id(update: Update) -> str | None:
    """Extract a single quiz identifier from a message's inline keyboard.

    Each quiz message has multiple buttons that all refer to the same quiz.
    We pick the first match and return ONE id to avoid per-message duplicates.

    Priority:
      1. ``switch_inline_query`` like ``quiz:XXXXXXXX``
      2. ``url`` matching ``https://t.me/QuizBot?start=XXXXXXXX``
    """
    msg = update.message
    if not msg or not msg.reply_markup:
        return None

    for row in msg.reply_markup.inline_keyboard:
        for button in row:
            # Primary: switch_inline_query  (e.g. "quiz:Z5rvaCWu")
            if button.switch_inline_query:
                return button.switch_inline_query

            # Fallback: url  (e.g. "https://t.me/QuizBot?start=Z5rvaCWu")
            if button.url:
                match = re.search(
                    r"t\.me/QuizBot\?start(?:group)?=(\w+)", button.url
                )
                if match:
                    return f"quiz:{match.group(1)}"

    return None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — show a welcome message."""
    await update.message.reply_text(
        "<b>Quiz Link Extractor Bot</b>\n\n"
        "1. Send /prepare to start collecting quiz messages.\n"
        "2. Forward all the @QuizBot quiz messages to me.\n"
        "3. Send /finish to get a <code>.txt</code> file with all quiz links.",
        parse_mode=ParseMode.HTML,
    )


async def cmd_prepare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /prepare — begin a new collection session."""
    chat_id = update.effective_chat.id
    _sessions[chat_id] = {}          # fresh ordered dict (used as ordered set)
    _active.add(chat_id)
    LOGGER.info("Session started for chat %s", chat_id)
    await update.message.reply_text(
        "Session started. Forward the quiz messages now.\n"
        "When you're done, send /finish."
    )


async def cmd_finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /finish — end session and send the .txt file."""
    chat_id = update.effective_chat.id

    if chat_id not in _active:
        await update.message.reply_text(
            "No active session. Send /prepare first."
        )
        return

    quiz_ids = list(_sessions.pop(chat_id, {}).keys())
    _active.discard(chat_id)

    if not quiz_ids:
        await update.message.reply_text(
            "No quiz links were collected. "
            "Make sure you forward @QuizBot quiz messages after /prepare."
        )
        return

    # Build the file content: one "@QuizBot <id>" per line
    lines = [f"@QuizBot {qid}" for qid in quiz_ids]
    content = "\n".join(lines) + "\n"

    # Send as a .txt document
    file = io.BytesIO(content.encode("utf-8"))
    file.name = "quiz_links.txt"

    await update.message.reply_document(
        document=file,
        caption=f"Extracted <b>{len(quiz_ids)}</b> unique quiz link(s).",
        parse_mode=ParseMode.HTML,
    )
    LOGGER.info("Sent %d unique quiz links to chat %s", len(quiz_ids), chat_id)


async def collect_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect quiz IDs from forwarded messages while session is active."""
    chat_id = update.effective_chat.id

    if chat_id not in _active:
        return  # silently ignore if no session

    quiz_id = _extract_quiz_id(update)

    if quiz_id:
        session = _sessions.setdefault(chat_id, {})
        if quiz_id in session:
            # Already seen — skip silently
            return
        session[quiz_id] = None        # add to ordered set
        count = len(session)
        await update.message.reply_text(
            f"Got it! ({count} unique quiz{'es' if count != 1 else ''} so far)"
        )
    # If the message has no quiz data we silently skip it


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("prepare", cmd_prepare))
    application.add_handler(CommandHandler("finish", cmd_finish))

    # Catch all non-command messages (forwarded quizzes)
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, collect_quiz)
    )

    LOGGER.info("Quiz Link Extractor Bot started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
