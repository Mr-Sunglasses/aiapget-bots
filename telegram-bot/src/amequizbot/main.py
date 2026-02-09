import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Load environment variables from .env file
load_dotenv()

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger("amequizbot")


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


def _extract_file_name(text: str) -> str:
    """Extract 'No. XX Date : DD Month YYYY  Topic : ...' from quiz intro text."""
    if not text:
        return ""

    # Try to match the quiz name between single quotes: 'No. 75 Date : ... @username'
    quote_match = re.search(r"'(No\.[^']+)'", text)
    if quote_match:
        content = quote_match.group(1)
        # Remove @mentions from the end
        content = re.sub(r"\s*@\w+\s*$", "", content)
        return content.strip()

    # Fallback: look for the pattern directly in the text
    pattern = r"(No\.\s*\d+\s*Date\s*:\s*.+?)\s*(?:@\w+|$)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return ""


def _extract_topic_title(text: str) -> str:
    """Extract 'Topic : ... by @...' part from text, or return empty string if not found."""
    if not text:
        return ""
    
    # Look for "Topic :" pattern including "by @username" part
    # Pattern: Topic : ... by @username (captures everything including "by @username")
    pattern = r"Topic\s*:\s*([^'\n]+?by\s+@\w+)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    
    if match:
        topic_text = match.group(1).strip()
        # Return with "Topic :" prefix
        return f"Topic : {topic_text}"
    
    # Fallback: if "by @username" not found, capture until end of line or quote
    pattern_fallback = r"Topic\s*:\s*([^'\n]+)"
    match_fallback = re.search(pattern_fallback, text, re.IGNORECASE)
    
    if match_fallback:
        topic_text = match_fallback.group(1).strip()
        return f"Topic : {topic_text}"
    
    return ""


def _clean_question_number(question: str) -> str:
    """Remove patterns like [1/28], phone numbers, mentions, etc. from question."""
    if not question:
        return question
    
    cleaned = question
    
    # Remove patterns from the beginning (in order of specificity):
    # 1. Pattern like [1/28] @mention phone\n
    cleaned = re.sub(r"^\[\d+/\d+\]\s*(?:@\w+\s*)?(?:\d{10}\s*)?\n?", "", cleaned, flags=re.IGNORECASE)
    
    # 2. Mentions like @Aiapgetmadeeasy followed by phone and newline
    cleaned = re.sub(r"^@\w+\s+\d{10}\s*\n?", "", cleaned, flags=re.IGNORECASE)
    
    # 3. Mentions like @Aiapgetmadeeasy followed by newline/space
    cleaned = re.sub(r"^@\w+\s*\n?", "", cleaned, flags=re.IGNORECASE)
    
    # 4. Phone numbers (10 digits) followed by newline/space
    cleaned = re.sub(r"^\d{10}\s*\n?", "", cleaned)
    
    # Remove patterns from the end:
    # Pattern like [6/25] @aiapgetmadeeasy 9336237929 at the end
    cleaned = re.sub(r"\s*\[\d+/\d+\]\s*(?:@\w+\s+)?\d{10}\s*$", "", cleaned, flags=re.IGNORECASE)
    
    # Pattern like [6/25] @aiapgetmadeeasy at the end
    cleaned = re.sub(r"\s*\[\d+/\d+\]\s*@\w+\s*$", "", cleaned, flags=re.IGNORECASE)
    
    # Pattern like [6/25] at the end
    cleaned = re.sub(r"\s*\[\d+/\d+\]\s*$", "", cleaned)
    
    # Remove trailing phone numbers
    cleaned = re.sub(r"\s+\d{10}\s*$", "", cleaned)
    
    return cleaned.strip()


def _extract_poll_data(payload: dict, prefix_text: str = None) -> dict:
    poll = payload.get("poll")
    if poll is None:
        poll = payload.get("message", {}).get("poll")
    if poll is None:
        raise ValueError("Missing message.poll data.")

    options = poll.get("options") or []
    extracted_options = [
        {
            "text": option.get("text"),
            "voter_count": option.get("voter_count"),
        }
        for option in options
    ]

    question = poll.get("question") or ""
    if prefix_text:
        question = f"{prefix_text}\n{question}".strip()
    
    # Clean question number pattern like [1/28] from the beginning
    question = _clean_question_number(question)

    result = {
        "question": question,
        "options": extracted_options,
        "total_voter_count": poll.get("total_voter_count"),
        "is_closed": poll.get("is_closed"),
        "is_anonymous": poll.get("is_anonymous"),
        "type": poll.get("type"),
        "allows_multiple_answers": poll.get("allows_multiple_answers"),
        "correct_option_id": poll.get("correct_option_id"),
        "explanation": poll.get("explanation"),
        "explanation_entities": poll.get("explanation_entities"),
    }
    
    return result


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Send /prepare to start collecting poll JSON, then /finish to export."
    )


async def prepare(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["collecting"] = True
    context.user_data["items"] = []
    context.user_data["current_title"] = None
    context.user_data["file_name"] = None
    context.user_data["pending_text"] = None
    await update.message.reply_text(
        "Ready. Send JSON messages containing message.poll. Use /finish when done."
    )


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    items = context.user_data.get("items") or []
    current_title = context.user_data.get("current_title") or ""
    file_name = context.user_data.get("file_name") or ""
    context.user_data["collecting"] = False

    if not items:
        await update.message.reply_text("No poll data collected.")
        return

    output_dir = Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"polls_{update.effective_chat.id}_{timestamp}.json"

    # Create output structure: dict with file_name, then array of title + poll objects
    output_data = {
        "file_name": file_name,
        "data": [current_title] + items,
    }

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(output_data, handle, ensure_ascii=False, indent=2)

    with output_path.open("rb") as handle:
        await update.message.reply_document(
            document=handle,
            filename=output_path.name,
            caption=f"Exported {len(items)} poll entries.",
        )


async def handle_json_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("collecting"):
        await update.message.reply_text("Send /prepare before sending JSON data.")
        return

    if not update.message or not update.message.text:
        await update.message.reply_text("Please send the JSON as text.")
        return

    raw_text = _strip_code_fences(update.message.text)
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        await update.message.reply_text(f"Invalid JSON: {exc.msg}")
        return

    # Check if message has text but no poll
    message = payload.get("message", {})
    message_text = message.get("text")
    has_poll = payload.get("poll") is not None or message.get("poll") is not None

    if message_text and not has_poll:
        # Extract topic title if present
        topic_title = _extract_topic_title(message_text)
        if topic_title:
            # If title found, store it but don't prepend to questions
            context.user_data["current_title"] = topic_title
            # Also extract file_name from the intro text
            file_name = _extract_file_name(message_text)
            if file_name:
                context.user_data["file_name"] = file_name
            await update.message.reply_text(f"Saved title: {topic_title}")
        else:
            # If no title, store text to prepend to next poll question
            context.user_data["pending_text"] = message_text
            await update.message.reply_text(
                f"Saved text (will be prepended to next poll): {message_text[:100]}..."
                if len(message_text) > 100
                else f"Saved text (will be prepended to next poll): {message_text}"
            )
        return

    # Try to extract poll data
    try:
        prefix_text = context.user_data.get("pending_text")
        extracted = _extract_poll_data(payload, prefix_text=prefix_text)
        # Clear pending text after using it
        if prefix_text:
            context.user_data["pending_text"] = None
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    items = context.user_data.setdefault("items", [])
    items.append(extracted)

    question_preview = (extracted.get("question") or "").strip().splitlines()[0]
    if len(question_preview) > 120:
        question_preview = f"{question_preview[:117]}..."

    await update.message.reply_text(
        f"Saved poll #{len(items)}: {question_preview or 'Question saved.'}"
    )


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("prepare", prepare))
    application.add_handler(CommandHandler("finish", finish))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_json_message)
    )

    LOGGER.info("Bot started.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
