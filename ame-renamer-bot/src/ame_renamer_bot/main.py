import io
import logging
import os
import zipfile
from dataclasses import dataclass, field

from dotenv import load_dotenv
from telegram import Document, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger("ame-renamer-bot")

# Conversation states
ASK_PREFIX, ASK_RANGE, COLLECT_FILES = range(3)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ALLOWED_MIMES = {DOCX_MIME, XLSX_MIME}
ALLOWED_EXTS = {".docx", ".xlsx"}


@dataclass
class Session:
    prefix: str = ""
    start: int = 0
    end: int = 0
    # Pending buffer: list of (original_filename, file_id, ext)
    pending: list = field(default_factory=list)
    # Completed pairs: list of (docx_file_id, xlsx_file_id, number)
    pairs: list = field(default_factory=list)


def _get_session(context: ContextTypes.DEFAULT_TYPE) -> Session:
    if "session" not in context.user_data:
        context.user_data["session"] = Session()
    return context.user_data["session"]


def _reset_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["session"] = Session()


def _file_ext(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _reset_session(context)
    await update.message.reply_text(
        "Welcome to the File Renamer Bot!\n\n"
        "I will rename your .docx and .xlsx file pairs with a prefix and number sequence.\n\n"
        "Send /rename to begin, or /cancel to stop at any time."
    )
    return ConversationHandler.END


async def rename_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _reset_session(context)
    await update.message.reply_text(
        "Step 1/2 — Please send me the *prefix* for the files.\n\n"
        "Example: `Quiz-abc`",
        parse_mode="Markdown",
    )
    return ASK_PREFIX


async def ask_prefix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    prefix = update.message.text.strip()
    if not prefix:
        await update.message.reply_text("Prefix cannot be empty. Please try again.")
        return ASK_PREFIX

    session = _get_session(context)
    session.prefix = prefix

    await update.message.reply_text(
        f"Prefix set to: `{prefix}`\n\n"
        "Step 2/2 — Please send me the *number range* in the format `start-end`.\n\n"
        "Example: `35-67`",
        parse_mode="Markdown",
    )
    return ASK_RANGE


async def ask_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    parts = text.split("-")
    if len(parts) != 2:
        await update.message.reply_text(
            "Invalid format. Please send the range as `start-end` (e.g. `35-67`).",
            parse_mode="Markdown",
        )
        return ASK_RANGE

    try:
        start_num = int(parts[0].strip())
        end_num = int(parts[1].strip())
    except ValueError:
        await update.message.reply_text(
            "Both start and end must be integers. Try again (e.g. `35-67`).",
            parse_mode="Markdown",
        )
        return ASK_RANGE

    if start_num > end_num:
        await update.message.reply_text(
            "Start must be less than or equal to end. Try again.",
        )
        return ASK_RANGE

    session = _get_session(context)
    session.start = start_num
    session.end = end_num
    total = end_num - start_num + 1

    await update.message.reply_text(
        f"Range set to: `{start_num}` – `{end_num}` ({total} pairs expected).\n\n"
        f"Now send me {total * 2} files in pairs — first the `.docx`, then the `.xlsx` for each number.\n\n"
        "Each consecutive pair (.docx + .xlsx) will be assigned the next number in the range.\n\n"
        "Send /finish when all files have been uploaded.",
        parse_mode="Markdown",
    )
    return COLLECT_FILES


async def collect_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    doc: Document = update.message.document
    if doc is None:
        await update.message.reply_text("Please send a file (.docx or .xlsx).")
        return COLLECT_FILES

    filename = doc.file_name or ""
    ext = _file_ext(filename)
    mime = doc.mime_type or ""

    if ext not in ALLOWED_EXTS and mime not in ALLOWED_MIMES:
        await update.message.reply_text(
            f"Unsupported file type: `{filename}`\n"
            "Only `.docx` and `.xlsx` files are accepted.",
            parse_mode="Markdown",
        )
        return COLLECT_FILES

    # Normalise extension from mime if filename has no recognised ext
    if ext not in ALLOWED_EXTS:
        ext = ".docx" if mime == DOCX_MIME else ".xlsx"

    session = _get_session(context)
    session.pending.append((filename, doc.file_id, ext))

    # Try to form pairs from pending buffer
    while len(session.pending) >= 2:
        first_name, first_id, first_ext = session.pending[0]
        second_name, second_id, second_ext = session.pending[1]

        # We need one .docx and one .xlsx in any order
        if {first_ext, second_ext} == {".docx", ".xlsx"}:
            docx_id = first_id if first_ext == ".docx" else second_id
            xlsx_id = first_id if first_ext == ".xlsx" else second_id
            session.pending = session.pending[2:]
            num = session.start + len(session.pairs)
            session.pairs.append((docx_id, xlsx_id, num))
            total_expected = session.end - session.start + 1
            await update.message.reply_text(
                f"Pair {len(session.pairs)}/{total_expected} received "
                f"→ will be renamed to `{session.prefix}-{num}`",
                parse_mode="Markdown",
            )
        else:
            # Two files of same type — cannot pair, drop first and warn
            await update.message.reply_text(
                f"Got two `{first_ext}` files in a row (`{first_name}` and `{second_name}`). "
                f"Dropping `{first_name}` — please re-send files in .docx/.xlsx pairs.",
                parse_mode="Markdown",
            )
            session.pending = session.pending[1:]

    total_expected = session.end - session.start + 1
    remaining_pairs = total_expected - len(session.pairs)

    if remaining_pairs <= 0:
        await update.message.reply_text(
            f"All {total_expected} pairs received! Send /finish to download renamed files."
        )
    else:
        buffered = len(session.pending)
        await update.message.reply_text(
            f"File received. {remaining_pairs} pair(s) remaining"
            + (f" ({buffered} file(s) buffered)." if buffered else "."),
        )

    return COLLECT_FILES


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    session = _get_session(context)

    if not session.pairs:
        await update.message.reply_text(
            "No complete pairs yet. Send .docx and .xlsx files in pairs first."
        )
        return COLLECT_FILES

    if session.pending:
        await update.message.reply_text(
            f"Warning: {len(session.pending)} unmatched file(s) were discarded "
            f"({', '.join(n for n, _, _ in session.pending)})."
        )

    await update.message.reply_text(
        f"Processing {len(session.pairs)} pair(s)… please wait."
    )

    # Build zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for docx_id, xlsx_id, num in session.pairs:
            new_name = f"{session.prefix}-{num}"

            # Download docx
            docx_file = await context.bot.get_file(docx_id)
            docx_bytes = await docx_file.download_as_bytearray()
            zf.writestr(f"{new_name}.docx", bytes(docx_bytes))

            # Download xlsx
            xlsx_file = await context.bot.get_file(xlsx_id)
            xlsx_bytes = await xlsx_file.download_as_bytearray()
            zf.writestr(f"{new_name}.xlsx", bytes(xlsx_bytes))

    zip_buffer.seek(0)
    zip_name = f"{session.prefix}-{session.start}-{session.end}.zip"

    await update.message.reply_document(
        document=zip_buffer,
        filename=zip_name,
        caption=(
            f"Done! {len(session.pairs)} pair(s) renamed.\n"
            f"Files: {session.prefix}-{session.start} … {session.prefix}-{session.end}"
        ),
    )

    _reset_session(context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _reset_session(context)
    await update.message.reply_text(
        "Cancelled. Send /rename to start over."
    )
    return ConversationHandler.END


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    application = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("rename", rename_start)],
        states={
            ASK_PREFIX: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_prefix)],
            ASK_RANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_range)],
            COLLECT_FILES: [
                MessageHandler(filters.Document.ALL, collect_file),
                CommandHandler("finish", finish),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv)

    LOGGER.info("Renamer bot started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
