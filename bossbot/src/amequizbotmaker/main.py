"""All-in-one Telegram Quiz Bot.

Flow
----
1.  User sends ``/start``   → welcome message.
2.  User sends ``/prepare`` → bot enters *collecting* mode.
3.  User **forwards quiz messages** (polls) to the bot.
    • The bot receives each forwarded message as a native Telegram Update.
    • It extracts the poll payload, cleans the question text, and stores it.
    • For non-poll text messages it tries to extract a topic title / file name.
4.  User sends ``/finish``  → bot assembles the combined JSON, generates
    **.xlsx** and **.docx** exports, and sends all three files back.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

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

from amequizbotmaker.extractors import (
    extract_file_name,
    extract_poll_data,
    extract_topic_title,
    strip_code_fences,
    update_to_json,
    wrap_code,
    MAX_MESSAGE_LENGTH,
    CODE_WRAPPER_OVERHEAD,
)
from amequizbotmaker.exporters import generate_docx, generate_xlsx, get_poll_count

load_dotenv()

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger("amequizbotmaker")

DATA_DIR = Path("data")


# ── /start ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome the user and explain available commands."""
    await update.message.reply_text(
        "Welcome to the AME Quiz Bot Maker!\n\n"
        "Commands:\n"
        "  /prepare  – start collecting quiz messages\n"
        "  /finish   – export collected quizzes to JSON, XLSX & DOCX\n"
        "  /json     – echo the raw JSON of the next message (debug)\n"
        "  /cancel   – cancel current collection\n\n"
        "After /prepare, simply **forward quiz messages** to me."
    )


# ── /prepare ──────────────────────────────────────────────────────────────

async def prepare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enter collecting mode."""
    context.user_data["collecting"] = True
    context.user_data["items"] = []
    context.user_data["current_title"] = None
    context.user_data["file_name"] = None
    context.user_data["pending_text"] = None
    context.user_data["json_debug"] = False
    await update.message.reply_text(
        "Ready!  Forward quiz messages to me now.\n"
        "Send /finish when you're done."
    )


# ── /cancel ───────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel the current collection."""
    items = context.user_data.get("items") or []
    context.user_data["collecting"] = False
    context.user_data["items"] = []
    context.user_data["current_title"] = None
    context.user_data["file_name"] = None
    context.user_data["pending_text"] = None
    await update.message.reply_text(
        f"Collection cancelled. {len(items)} item(s) discarded."
    )


# ── /json  (debug echo) ──────────────────────────────────────────────────

async def json_debug_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle JSON-echo debug mode for the next message."""
    current = context.user_data.get("json_debug", False)
    context.user_data["json_debug"] = not current
    state = "ON" if not current else "OFF"
    await update.message.reply_text(f"JSON debug echo is now {state}.")


# ── /finish ───────────────────────────────────────────────────────────────

async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export all collected polls to JSON + XLSX + DOCX and send to user."""
    items: list[dict] = context.user_data.get("items") or []
    current_title: str = context.user_data.get("current_title") or ""
    file_name: str = context.user_data.get("file_name") or ""
    context.user_data["collecting"] = False

    if not items:
        await update.message.reply_text("No quiz data collected yet. Nothing to export.")
        return

    await update.message.reply_text(
        f"Processing {len(items)} question(s). Generating files …"
    )

    # ── Build combined JSON ───────────────────────────────────────────
    output_data = {
        "file_name": file_name,
        "data": [current_title] + items,
    }

    # Persist JSON to data/ dir as well
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    chat_id = update.effective_chat.id
    json_filename = f"polls_{chat_id}_{timestamp}.json"
    json_path = DATA_DIR / json_filename

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(output_data, fh, ensure_ascii=False, indent=2)

    # ── Generate XLSX & DOCX ─────────────────────────────────────────
    base_name = file_name if file_name else "questions_output"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        xlsx_path = tmp / f"{base_name}.xlsx"
        docx_path = tmp / f"{base_name}.docx"

        try:
            generate_xlsx(output_data, xlsx_path)
            generate_docx(output_data, docx_path)
        except Exception as exc:
            LOGGER.exception("Export failed")
            await update.message.reply_text(f"Export failed: {exc}")
            return

        # ── Send all three files ─────────────────────────────────────
        poll_count = get_poll_count(output_data)

        with json_path.open("rb") as fh:
            await update.message.reply_document(
                document=fh,
                filename=json_filename,
                caption=f"JSON export ({poll_count} questions)",
            )

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

    # Reset state
    context.user_data["items"] = []
    context.user_data["current_title"] = None
    context.user_data["file_name"] = None
    context.user_data["pending_text"] = None

    await update.message.reply_text("Done! Send /prepare to start a new batch.")


# ── Handle forwarded polls (native poll messages) ─────────────────────────

async def handle_poll_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a forwarded message that contains a native Telegram poll/quiz."""
    # JSON debug echo
    if context.user_data.get("json_debug"):
        context.user_data["json_debug"] = False
        raw = update_to_json(update)
        usable = MAX_MESSAGE_LENGTH - CODE_WRAPPER_OVERHEAD
        if len(raw) <= usable:
            await update.message.reply_text(wrap_code(raw), parse_mode=ParseMode.HTML)
        else:
            chunks, current = [], ""
            for line in raw.splitlines(keepends=True):
                if len(current) + len(line) > usable:
                    chunks.append(current)
                    current = line
                else:
                    current += line
            if current:
                chunks.append(current)
            for i, chunk in enumerate(chunks, 1):
                await update.message.reply_text(
                    wrap_code(chunk, part_label=f"[Part {i}/{len(chunks)}]"),
                    parse_mode=ParseMode.HTML,
                )
        return

    if not context.user_data.get("collecting"):
        await update.message.reply_text(
            "Send /prepare first to start collecting quizzes."
        )
        return

    # Convert the update to a dict so we can use extract_poll_data
    payload = update.to_dict()

    try:
        prefix_text = context.user_data.get("pending_text")
        extracted = extract_poll_data(payload, prefix_text=prefix_text)
        if prefix_text:
            context.user_data["pending_text"] = None
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    items: list[dict] = context.user_data.setdefault("items", [])
    items.append(extracted)

    question_preview = (extracted.get("question") or "").strip().splitlines()[0]
    if len(question_preview) > 120:
        question_preview = f"{question_preview[:117]}…"

    await update.message.reply_text(
        f"Saved quiz #{len(items)}: {question_preview or 'Question saved.'}"
    )


# ── Handle text messages (JSON paste or intro text) ───────────────────────

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages.

    These can be:
    • JSON-encoded update payloads pasted from json-echo-bot
    • Intro / title text for the quiz batch
    """
    if not update.message or not update.message.text:
        return

    # JSON debug echo
    if context.user_data.get("json_debug"):
        context.user_data["json_debug"] = False
        raw = update_to_json(update)
        usable = MAX_MESSAGE_LENGTH - CODE_WRAPPER_OVERHEAD
        if len(raw) <= usable:
            await update.message.reply_text(wrap_code(raw), parse_mode=ParseMode.HTML)
        else:
            chunks, current = [], ""
            for line in raw.splitlines(keepends=True):
                if len(current) + len(line) > usable:
                    chunks.append(current)
                    current = line
                else:
                    current += line
            if current:
                chunks.append(current)
            for i, chunk in enumerate(chunks, 1):
                await update.message.reply_text(
                    wrap_code(chunk, part_label=f"[Part {i}/{len(chunks)}]"),
                    parse_mode=ParseMode.HTML,
                )
        return

    if not context.user_data.get("collecting"):
        await update.message.reply_text(
            "Send /prepare first to start collecting quizzes."
        )
        return

    raw_text = update.message.text

    # ── Try parsing as JSON (pasted from json-echo-bot) ───────────────
    stripped = strip_code_fences(raw_text)
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None

        if payload and isinstance(payload, dict):
            message = payload.get("message", {})
            message_text = message.get("text")
            has_poll = (
                payload.get("poll") is not None
                or message.get("poll") is not None
            )

            if message_text and not has_poll:
                # Intro text — extract title / file name
                topic_title = extract_topic_title(message_text)
                if topic_title:
                    context.user_data["current_title"] = topic_title
                    fn = extract_file_name(message_text)
                    if fn:
                        context.user_data["file_name"] = fn
                    await update.message.reply_text(f"Saved title: {topic_title}")
                else:
                    context.user_data["pending_text"] = message_text
                    preview = message_text[:100] + "…" if len(message_text) > 100 else message_text
                    await update.message.reply_text(
                        f"Saved text (will be prepended to next poll): {preview}"
                    )
                return

            if has_poll:
                try:
                    prefix_text = context.user_data.get("pending_text")
                    extracted = extract_poll_data(payload, prefix_text=prefix_text)
                    if prefix_text:
                        context.user_data["pending_text"] = None
                except ValueError as exc:
                    await update.message.reply_text(str(exc))
                    return

                items: list[dict] = context.user_data.setdefault("items", [])
                items.append(extracted)

                question_preview = (extracted.get("question") or "").strip().splitlines()[0]
                if len(question_preview) > 120:
                    question_preview = f"{question_preview[:117]}…"

                await update.message.reply_text(
                    f"Saved poll #{len(items)}: {question_preview or 'Question saved.'}"
                )
                return

    # ── Plain text: try to extract title / file_name ──────────────────
    topic_title = extract_topic_title(raw_text)
    if topic_title:
        context.user_data["current_title"] = topic_title
        fn = extract_file_name(raw_text)
        if fn:
            context.user_data["file_name"] = fn
        await update.message.reply_text(f"Saved title: {topic_title}")
    else:
        context.user_data["pending_text"] = raw_text
        preview = raw_text[:100] + "…" if len(raw_text) > 100 else raw_text
        await update.message.reply_text(
            f"Saved text (will be prepended to next poll): {preview}"
        )


# ── Handle document uploads (.json files) ────────────────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a .json file sent as a document attachment."""
    doc = update.message.document
    if not doc or not doc.file_name or not doc.file_name.endswith(".json"):
        await update.message.reply_text("Please send a .json file.")
        return

    tg_file = await doc.get_file()

    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = Path(tmpdir) / doc.file_name
        await tg_file.download_to_drive(json_path)
        raw = json_path.read_text(encoding="utf-8")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        await update.message.reply_text(f"Invalid JSON: {exc.msg}")
        return

    inner = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(inner, list) or len(inner) < 2:
        await update.message.reply_text(
            "Expected a JSON array (or object with a 'data' key) containing "
            "a title string and poll objects."
        )
        return

    poll_count = get_poll_count(data)
    await update.message.reply_text(
        f"Processing {poll_count} questions from file. Generating exports …"
    )

    from amequizbotmaker.exporters import get_file_name as _get_file_name

    base_name = _get_file_name(data) or "questions_output"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        xlsx_path = tmp / f"{base_name}.xlsx"
        docx_path = tmp / f"{base_name}.docx"

        try:
            generate_xlsx(data, xlsx_path)
            generate_docx(data, docx_path)
        except Exception as exc:
            LOGGER.exception("Export failed")
            await update.message.reply_text(f"Export failed: {exc}")
            return

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
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set.  "
            "Copy .env.example to .env and add your bot token."
        )

    application = Application.builder().token(token).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("prepare", prepare))
    application.add_handler(CommandHandler("finish", finish))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("json", json_debug_toggle))

    # Forwarded polls / quizzes (native poll messages)
    application.add_handler(
        MessageHandler(filters.POLL, handle_poll_message)
    )

    # Document uploads (.json files for direct export)
    application.add_handler(
        MessageHandler(filters.Document.ALL, handle_document)
    )

    # Plain text (JSON paste from json-echo-bot, or intro text)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )

    LOGGER.info("AME Quiz Bot Maker started — send /start for help.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
