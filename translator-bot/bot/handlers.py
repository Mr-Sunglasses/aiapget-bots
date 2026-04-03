"""Telegram bot handlers for the bilingual quiz converter."""

import logging
import os
import tempfile
import time
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.pipeline import process_docx, process_xlsx, process_pair

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", "20"))
CACHE_PATH = os.environ.get("TRANSLATION_CACHE_PATH", ".translation_cache.json")
USAGE_LOG_PATH = os.environ.get("USAGE_LOG_PATH", ".usage_log.json")
PENDING_TIMEOUT = 600  # 10 minutes


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Welcome to BilingualBot!\n\n"
        "Send me a quiz .docx or .xlsx file, and I'll convert it to a bilingual "
        "(English + Hindi) version using AI translation.\n\n"
        "You can send both files (DOCX + XLSX pair) for synchronized conversion, "
        "or just one at a time.\n\n"
        "Commands:\n"
        "/skip — Process the pending file without waiting for its pair\n"
        "/help — Show this message"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 How to use BilingualBot:\n\n"
        "1. Send a .docx file → I'll ask for the matching .xlsx\n"
        "2. Send the .xlsx (or /skip to process DOCX only)\n"
        "3. Get back bilingual versions of both files\n\n"
        "Files must be Ayurvedic quiz format with #Question markers.\n"
        "Max file size: 20 MB."
    )


async def skip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending_docx = context.user_data.get("pending_docx")
    pending_xlsx = context.user_data.get("pending_xlsx")

    if pending_docx:
        path, original_name, _ = pending_docx
        context.user_data.pop("pending_docx", None)
        await _process_single(update, context, path, "docx", original_name)
    elif pending_xlsx:
        path, original_name, _ = pending_xlsx
        context.user_data.pop("pending_xlsx", None)
        await _process_single(update, context, path, "xlsx", original_name)
    else:
        await update.message.reply_text("No pending file to process.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc:
        return

    name = doc.file_name or ""
    ext = Path(name).suffix.lower()

    if ext not in (".docx", ".xlsx"):
        await update.message.reply_text("❌ Please send a .docx or .xlsx file")
        return

    size_mb = (doc.file_size or 0) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        await update.message.reply_text(f"❌ File too large ({size_mb:.1f} MB, max {MAX_FILE_SIZE_MB} MB)")
        return

    # Download file
    tg_file = await doc.get_file()
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    await tg_file.download_to_drive(tmp.name)
    tmp.close()

    now = time.time()

    if ext == ".docx":
        pending_xlsx = context.user_data.get("pending_xlsx")
        if pending_xlsx:
            xlsx_path, xlsx_name, ts = pending_xlsx
            context.user_data.pop("pending_xlsx", None)
            if now - ts < PENDING_TIMEOUT:
                await _process_pair(update, context, tmp.name, xlsx_path, name, xlsx_name)
                return
        context.user_data["pending_docx"] = (tmp.name, name, now)
        await update.message.reply_text(
            f"📄 Got your DOCX ({name}). Send the matching .xlsx now, or /skip to convert DOCX only."
        )

    elif ext == ".xlsx":
        pending_docx = context.user_data.get("pending_docx")
        if pending_docx:
            docx_path, docx_name, ts = pending_docx
            context.user_data.pop("pending_docx", None)
            if now - ts < PENDING_TIMEOUT:
                await _process_pair(update, context, docx_path, tmp.name, docx_name, name)
                return
        context.user_data["pending_xlsx"] = (tmp.name, name, now)
        await update.message.reply_text(
            f"📊 Got your XLSX ({name}). Send the matching .docx now, or /skip to convert XLSX only."
        )


async def _process_single(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    path: str,
    file_type: str,
    original_name: str = "",
) -> None:
    processing_msg = await update.message.reply_text("⏳ Processing... this may take a moment.")
    try:
        if file_type == "docx":
            output_path, stats = process_docx(path, CACHE_PATH, USAGE_LOG_PATH)
        else:
            output_path, stats = process_xlsx(path, CACHE_PATH, USAGE_LOG_PATH)

        if stats.total_questions == 0:
            await processing_msg.edit_text("❌ Could not find any questions. Is this the correct format?")
            return

        reply_name = original_name or Path(output_path).name
        await update.message.reply_document(
            document=open(output_path, "rb"),
            filename=reply_name,
        )
        await processing_msg.edit_text(_stats_message(stats))

    except ValueError as e:
        await processing_msg.edit_text(f"❌ {e}")
    except Exception:
        logger.exception("Processing failed")
        await processing_msg.edit_text("❌ Something went wrong. Please try again.")
    finally:
        _cleanup(path)


async def _process_pair(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    docx_path: str,
    xlsx_path: str,
    docx_name: str = "",
    xlsx_name: str = "",
) -> None:
    processing_msg = await update.message.reply_text("⏳ Processing pair... this may take a moment.")
    try:
        docx_out, xlsx_out, stats = process_pair(docx_path, xlsx_path, CACHE_PATH, USAGE_LOG_PATH)

        if stats.total_questions == 0:
            await processing_msg.edit_text("❌ Could not find any questions. Is this the correct format?")
            return

        await update.message.reply_document(
            document=open(docx_out, "rb"),
            filename=docx_name or Path(docx_out).name,
        )
        await update.message.reply_document(
            document=open(xlsx_out, "rb"),
            filename=xlsx_name or Path(xlsx_out).name,
        )
        await processing_msg.edit_text(_stats_message(stats))

    except ValueError as e:
        await processing_msg.edit_text(f"❌ {e}")
    except Exception:
        logger.exception("Pair processing failed")
        await processing_msg.edit_text("❌ Something went wrong. Please try again.")
    finally:
        _cleanup(docx_path, xlsx_path)


def _stats_message(stats) -> str:
    cached = "Yes" if stats.cache_hit else "No"
    msg = (
        f"✅ {stats.total_questions} questions converted\n"
        f"💰 Cost: ~${stats.cost_usd:.4f} | "
        f"Tokens: {stats.input_tokens:,} in / {stats.output_tokens:,} out\n"
        f"📦 Cached: {cached}"
    )
    if stats.errors:
        warning_lines = "\n".join(f"  • {e}" for e in stats.errors)
        msg += f"\n\n⚠️ Translation warnings:\n{warning_lines}"
    return msg


def _cleanup(*paths: str) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass
        bilingual = Path(p)
        bilingual_path = bilingual.parent / f"{bilingual.stem}_bilingual{bilingual.suffix}"
        try:
            os.unlink(bilingual_path)
        except OSError:
            pass


def register_handlers(app) -> None:
    """Register all handlers on the Application."""
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("skip", skip_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
