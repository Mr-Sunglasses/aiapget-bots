"""Extract and clean poll / quiz data from raw Telegram update payloads.

Combines the JSON-echo logic (json-echo-bot) with the poll-extraction and
text-cleaning logic (telegram-bot).
"""

import html
import json
import re

# Telegram message-length limit & overhead for <pre> wrapper
MAX_MESSAGE_LENGTH = 4096
CODE_WRAPPER_OVERHEAD = 40


# ---------------------------------------------------------------------------
# Low-level helpers (from json-echo-bot)
# ---------------------------------------------------------------------------

def wrap_code(text: str, part_label: str = "") -> str:
    """Wrap *text* in an HTML ``<pre>`` code block, escaping HTML entities."""
    escaped = html.escape(text)
    if part_label:
        return f"<b>{html.escape(part_label)}</b>\n<pre>{escaped}</pre>"
    return f"<pre>{escaped}</pre>"


def update_to_json(update) -> str:
    """Return pretty-printed JSON string from a Telegram *Update* object."""
    payload = update.to_dict()
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Code-fence stripping
# ---------------------------------------------------------------------------

def strip_code_fences(text: str) -> str:
    """Remove surrounding ``` code fences from *text*."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Text cleaning helpers (from telegram-bot)
# ---------------------------------------------------------------------------

def extract_file_name(text: str) -> str:
    """Extract quiz name from intro text (between single quotes or directly)."""
    if not text:
        return ""

    # Match content between single quotes starting with "Quiz no." / "Quiz no-" or "No." / "No-"
    quote_match = re.search(r"'((?:Quiz\s+)?[Nn]o[.\-].+?)'{1,2}", text, re.DOTALL)
    if quote_match:
        content = quote_match.group(1).strip()
        # Strip trailing "BY @mention phone" variants
        content = re.sub(r"\s+BY\s+@\w+(?:\s+\d{6,12})?\s*$", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*@\w+\s*$", "", content)
        content = re.sub(r"\s+\d{6,12}\s*$", "", content)
        return content.strip()

    # Fallback: look for "Quiz no." / "Quiz no-" / "No." / "No-" pattern directly in text
    pattern = r"((?:Quiz\s+)?[Nn]o[.\-]\s*\d+\s*Date\s*[:\-]?\s*.+?)\s*(?:BY\s+@\w+|@\w+|$)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        content = match.group(1).strip()
        content = re.sub(r"\s+\d{6,12}\s*$", "", content)
        return content.strip()

    return ""


def extract_topic_title(text: str) -> str:
    """Extract ``Topic : ... by @...`` from *text*, or return ``""``."""
    if not text:
        return ""

    pattern = r"Topic\s*:\s*([^'\n]+?by\s+@\w+)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        return f"Topic : {match.group(1).strip()}"

    pattern_fallback = r"Topic\s*:\s*([^'\n]+)"
    match_fallback = re.search(pattern_fallback, text, re.IGNORECASE)
    if match_fallback:
        return f"Topic : {match_fallback.group(1).strip()}"

    return ""


def clean_question_number(question: str) -> str:
    """Remove ``[1/28]``, phone numbers, @mentions etc. from *question*."""
    if not question:
        return question

    cleaned = question

    # Beginning patterns
    cleaned = re.sub(
        r"^\[\d+/\d+\]\s*(?:@\w+\s*)?(?:\d{10}\s*)?\n?",
        "", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^@\w+\s+\d{10}\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^@\w+\s*\n?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\d{10}\s*\n?", "", cleaned)

    # End patterns
    cleaned = re.sub(
        r"\s*\[\d+/\d+\]\s*(?:@\w+\s+)?\d{10}\s*$",
        "", cleaned, flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*\[\d+/\d+\]\s*@\w+\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\[\d+/\d+\]\s*$", "", cleaned)
    cleaned = re.sub(r"\s+\d{10}\s*$", "", cleaned)

    return cleaned.strip()


# ---------------------------------------------------------------------------
# Poll extraction (from telegram-bot)
# ---------------------------------------------------------------------------

def extract_poll_data(payload: dict, prefix_text: str | None = None) -> dict:
    """Extract cleaned poll data from a raw Telegram update *payload* dict.

    Returns a dict with keys: question, options, total_voter_count, is_closed,
    is_anonymous, type, allows_multiple_answers, correct_option_id,
    explanation, explanation_entities.
    """
    poll = payload.get("poll")
    if poll is None:
        poll = payload.get("message", {}).get("poll")
    if poll is None:
        raise ValueError("Missing message.poll data.")

    options = poll.get("options") or []
    extracted_options = [
        {"text": opt.get("text"), "voter_count": opt.get("voter_count")}
        for opt in options
    ]

    question = poll.get("question") or ""
    if prefix_text:
        prefix = prefix_text.strip()
        poll_q = question.strip()
        # Normalize both (strip [N/N] @mention prefixes) before comparing to detect
        # duplication (e.g. "[6/25] @X\nMatch the following\nA..B..C.." prefix
        # + "[6/25] @X\nMatch the following" poll → use just the normalized prefix)
        norm_prefix = clean_question_number(prefix)
        norm_poll_q = clean_question_number(poll_q)
        if norm_poll_q and norm_prefix.startswith(norm_poll_q):
            question = norm_prefix
        else:
            question = f"{prefix}\n{poll_q}".strip()

    question = clean_question_number(question)

    return {
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
