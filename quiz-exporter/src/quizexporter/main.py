"""Telegram bot that receives quiz JSON and exports to XLSX / DOCX."""

import json
import logging
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from quizexporter.exporters import generate_docx, generate_xlsx, get_file_name, get_poll_count

load_dotenv()

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger("quizexporter")


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ── Handlers ──────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send me a quiz JSON array and I will export it to XLSX and DOCX.\n\n"
        "The JSON should be an array where the first element is the title "
        "string and the rest are poll objects."
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a .json file sent as a document."""
    doc = update.message.document
    if not doc.file_name.endswith(".json"):
        await update.message.reply_text("Please send a .json file.")
        return

    tg_file = await doc.get_file()

    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / doc.file_name
        await tg_file.download_to_drive(json_path)

        raw = json_path.read_text(encoding="utf-8")
        await _process_json(update, raw, tmpdir)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle JSON pasted as text."""
    if not update.message or not update.message.text:
        return

    raw = _strip_code_fences(update.message.text)
    # Quick check: must start with '[' or '{' to be valid quiz JSON
    if not raw.startswith("[") and not raw.startswith("{"):
        await update.message.reply_text(
            "Please send a JSON array or object with quiz data."
        )
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        await _process_json(update, raw, tmpdir)


async def _process_json(update: Update, raw_json: str, tmpdir: str) -> None:
    """Parse JSON, generate files, send them back."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        await update.message.reply_text(f"Invalid JSON: {exc.msg}")
        return

    # Accept both list format and dict format (with "data" key)
    inner = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(inner, list) or len(inner) < 2:
        await update.message.reply_text(
            "Expected a JSON array (or object with a 'data' key) containing a title string and poll objects."
        )
        return

    # Extract file_name and poll count
    file_name = get_file_name(data)
    poll_count = get_poll_count(data)

    await update.message.reply_text(
        f"Processing {poll_count} questions. Generating files..."
    )

    tmp = Path(tmpdir)

    # Use file_name from JSON for output filenames, fallback to defaults
    base_name = file_name if file_name else "questions_output"
    xlsx_path = tmp / f"{base_name}.xlsx"
    docx_path = tmp / f"{base_name}.docx"

    try:
        generate_xlsx(data, xlsx_path)
        generate_docx(data, docx_path)
    except Exception as exc:
        LOGGER.exception("Export failed")
        await update.message.reply_text(f"Export failed: {exc}")
        return

    # Send both files with file_name from JSON
    with xlsx_path.open("rb") as fh:
        await update.message.reply_document(
            document=fh,
            filename=f"{base_name}.xlsx",
            caption=f"XLSX export ({poll_count} questions)",
        )

    with docx_path.open("rb") as fh:
        await update.message.reply_document(
            document=fh,
            filename=f"{base_name}.docx",
            caption=f"DOCX export ({poll_count} questions)",
        )


# ── Entry point ───────────────────────────────────────────────────────────

def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.Document.ALL, handle_document)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    LOGGER.info("Quiz exporter bot started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
