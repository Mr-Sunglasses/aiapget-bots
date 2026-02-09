"""Quiz Attempt Bot – auto-attempt QuizBot quizzes and forward to another bot.

Workflow
--------
1.  User sends quiz links in any chat (Saved Messages works best).
    Supports single or multiple links, and .txt file uploads.
2.  The userbot queues all quiz IDs and processes them one by one.
3.  For each quiz: start with @QuizBot → auto-vote → forward to target bot.
4.  Waits 5–8 minutes between quizzes to avoid Telegram rate limits.
5.  Reports progress after each quiz.

Commands (send in any chat):
    quiz:XXXXX              – attempt one quiz
    quiz:AAA quiz:BBB ...   – attempt multiple quizzes (queue)
    /status                 – show queue status
    /cancel                 – cancel remaining quizzes
    Upload a .txt file      – one quiz ID per line (e.g. "quiz:XXXXX")
"""

import asyncio
import logging
import os
import random
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

load_dotenv()

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger("quizattemptbot")

# Regex to find quiz IDs — matches "quiz:Z5rvaCWu" anywhere in text
QUIZ_ID_RE = re.compile(r"quiz:(\w+)", re.IGNORECASE)

QUIZBOT_USERNAME = "QuizBot"

# ── Rate-limit settings ──────────────────────────────────────────────────
# Delay between each poll vote (seconds) — slows down voting to avoid flood
VOTE_DELAY_MIN = 1
VOTE_DELAY_MAX = 2

# Delay between quizzes in queue (seconds) — 1 to 2 minutes
QUIZ_DELAY_MIN = 1 * 60   # 60s = 1 min
QUIZ_DELAY_MAX = 2 * 60   # 120s = 2 min


# ── State ─────────────────────────────────────────────────────────────────


@dataclass
class QuizSession:
    """Tracks state for one active quiz attempt."""

    quiz_id: str
    queue_index: int = 0
    queue_total: int = 0
    quizbot_chat_id: int = 0
    forward_bot_id: int = 0
    trigger_chat_id: int = 0
    text_message_ids: list[int] = field(default_factory=list)
    poll_message_ids: list[int] = field(default_factory=list)
    forwarding: bool = False


# Global state
_session: QuizSession | None = None
_queue: list[str] = []
_resolved_quizbot_id: int = 0
_resolved_forward_id: int = 0
_trigger_chat_id: int = 0
_total_in_batch: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────


def _build_client() -> Client:
    """Build a Pyrogram Client from environment variables."""
    api_id = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    session_string = os.getenv("SESSION_STRING", "").strip()

    if not api_id or not api_hash:
        raise RuntimeError(
            "API_ID and API_HASH environment variables must be set. "
            "Get them from https://my.telegram.org"
        )

    if session_string and not session_string.startswith("optional"):
        return Client(
            "quiz_attemptbot",
            api_id=int(api_id),
            api_hash=api_hash,
            in_memory=True,
            session_string=session_string,
        )

    return Client(
        "quiz_attemptbot",
        api_id=int(api_id),
        api_hash=api_hash,
    )


def _get_forward_bot() -> str:
    """Return the username of the bot to forward quizzes to."""
    return os.getenv("FORWARD_BOT", "ameboss_bot").strip().lstrip("@")


async def _safe_action(coro, label: str = "action", retries: int = 3):
    """Execute a Pyrogram coroutine with FloodWait handling and retries."""
    for attempt in range(1, retries + 1):
        try:
            return await coro
        except FloodWait as e:
            wait = e.value
            LOGGER.warning(
                "FLOOD_WAIT %ds on %s — sleeping… (attempt %d/%d)",
                wait, label, attempt, retries,
            )
            await asyncio.sleep(wait + 1)
        except Exception as exc:
            LOGGER.error("%s failed: %s (attempt %d/%d)", label, exc, attempt, retries)
            if attempt == retries:
                raise
            await asyncio.sleep(2)
    return None


async def _resolve_bots(client: Client) -> bool:
    """Resolve QuizBot and forward bot chat IDs. Returns True on success."""
    global _resolved_quizbot_id, _resolved_forward_id

    if not _resolved_quizbot_id:
        try:
            chat = await client.get_chat(QUIZBOT_USERNAME)
            _resolved_quizbot_id = chat.id
            LOGGER.info("Resolved @%s → %d", QUIZBOT_USERNAME, _resolved_quizbot_id)
        except Exception as exc:
            LOGGER.error("Cannot resolve @%s: %s", QUIZBOT_USERNAME, exc)
            return False

    if not _resolved_forward_id:
        forward_bot = _get_forward_bot()
        try:
            chat = await client.get_chat(forward_bot)
            _resolved_forward_id = chat.id
            LOGGER.info("Resolved @%s → %d", forward_bot, _resolved_forward_id)
        except Exception as exc:
            LOGGER.error("Cannot resolve @%s: %s", forward_bot, exc)
            return False

    return True


async def _start_next_quiz(client: Client) -> None:
    """Pop the next quiz ID from the queue and start it."""
    global _session, _queue

    if _session is not None or not _queue:
        return

    quiz_id = _queue.pop(0)
    index = _total_in_batch - len(_queue)

    LOGGER.info(
        "━━━ Starting quiz %d/%d: quiz:%s ━━━",
        index, _total_in_batch, quiz_id,
    )

    _session = QuizSession(
        quiz_id=quiz_id,
        queue_index=index,
        queue_total=_total_in_batch,
        quizbot_chat_id=_resolved_quizbot_id,
        forward_bot_id=_resolved_forward_id,
        trigger_chat_id=_trigger_chat_id,
    )

    try:
        await _safe_action(
            client.send_message(_resolved_quizbot_id, f"/start {quiz_id}"),
            label=f"send /start {quiz_id}",
        )
        LOGGER.info("Sent /start %s to @%s", quiz_id, QUIZBOT_USERNAME)
    except Exception as exc:
        LOGGER.error("Failed to send /start for quiz:%s: %s", quiz_id, exc)
        _session = None
        if _queue:
            await _start_next_quiz(client)


async def _forward_to_bot(client: Client, session: QuizSession) -> None:
    """Forward collected messages to the target bot with /prepare and /finish."""
    global _session

    if session.forwarding:
        return
    session.forwarding = True

    forward_bot = _get_forward_bot()
    bot_id = session.forward_bot_id
    total = len(session.poll_message_ids)
    remaining = len(_queue)

    LOGGER.info(
        "Quiz %d/%d done! Forwarding %d poll(s) to @%s …",
        session.queue_index, session.queue_total, total, forward_bot,
    )

    BATCH_SIZE = 5

    try:
        # 1. /start + /prepare
        await _safe_action(client.send_message(bot_id, "/start"), "fwd /start")
        await asyncio.sleep(1)
        await _safe_action(client.send_message(bot_id, "/prepare"), "fwd /prepare")
        await asyncio.sleep(2)

        # 2. Forward intro text messages
        for msg_id in session.text_message_ids:
            try:
                await _safe_action(
                    client.forward_messages(
                        chat_id=bot_id,
                        from_chat_id=session.quizbot_chat_id,
                        message_ids=msg_id,
                    ),
                    label=f"forward intro {msg_id}",
                )
                await asyncio.sleep(0.5)
            except Exception as exc:
                LOGGER.warning("Failed to forward intro msg %d: %s", msg_id, exc)

        # 3. Forward poll messages in batches
        for i in range(0, total, BATCH_SIZE):
            batch = session.poll_message_ids[i : i + BATCH_SIZE]
            try:
                await _safe_action(
                    client.forward_messages(
                        chat_id=bot_id,
                        from_chat_id=session.quizbot_chat_id,
                        message_ids=batch,
                    ),
                    label=f"forward batch {i // BATCH_SIZE + 1}",
                )
            except Exception as exc:
                LOGGER.error("Batch failed: %s — sending one by one", exc)
                for msg_id in batch:
                    try:
                        await _safe_action(
                            client.forward_messages(
                                chat_id=bot_id,
                                from_chat_id=session.quizbot_chat_id,
                                message_ids=msg_id,
                            ),
                            label=f"forward msg {msg_id}",
                        )
                        await asyncio.sleep(1)
                    except Exception as inner_exc:
                        LOGGER.warning("Failed msg %d: %s", msg_id, inner_exc)
            await asyncio.sleep(1.5)

        # 4. /finish
        await _safe_action(client.send_message(bot_id, "/finish"), "fwd /finish")
        LOGGER.info("Forwarded quiz:%s (%d polls) to @%s.", session.quiz_id, total, forward_bot)

        # 5. Progress report
        try:
            if remaining > 0:
                delay = random.randint(QUIZ_DELAY_MIN, QUIZ_DELAY_MAX)
                delay_min = delay // 60
                delay_sec = delay % 60
                await client.send_message(
                    chat_id=session.trigger_chat_id,
                    text=(
                        f"[{session.queue_index}/{session.queue_total}] "
                        f"Quiz `{session.quiz_id}` done ({total} questions).\n"
                        f"{remaining} quiz(zes) remaining.\n"
                        f"Waiting {delay_min}m {delay_sec}s before next quiz…"
                    ),
                )
            else:
                delay = 0
                await client.send_message(
                    chat_id=session.trigger_chat_id,
                    text=(
                        f"[{session.queue_index}/{session.queue_total}] "
                        f"Quiz `{session.quiz_id}` done ({total} questions).\n"
                        f"All quizzes complete!"
                    ),
                )
        except Exception:
            delay = random.randint(QUIZ_DELAY_MIN, QUIZ_DELAY_MAX) if remaining > 0 else 0

    except Exception as exc:
        LOGGER.error("Forward failed for quiz:%s: %s", session.quiz_id, exc)
        delay = random.randint(QUIZ_DELAY_MIN, QUIZ_DELAY_MAX) if _queue else 0
        try:
            await client.send_message(
                chat_id=session.trigger_chat_id,
                text=f"Forward failed for quiz:{session.quiz_id}: {exc}",
            )
        except Exception:
            pass

    finally:
        _session = None

    # Start the next quiz after the cooldown
    if _queue:
        LOGGER.info("Cooling down %d seconds before next quiz…", delay)
        await asyncio.sleep(delay)
        await _start_next_quiz(client)
    else:
        LOGGER.info("━━━ All %d quizzes processed! ━━━", _total_in_batch)


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    global _session, _queue, _trigger_chat_id, _total_in_batch

    app = _build_client()

    # ── Handler 1: Detect quiz links (single or multiple) ─────────────

    @app.on_message(filters.text & filters.regex(QUIZ_ID_RE) & ~filters.user(QUIZBOT_USERNAME))
    async def handle_quiz_links(client: Client, message: Message) -> None:
        global _queue, _trigger_chat_id, _total_in_batch

        quiz_ids = QUIZ_ID_RE.findall(message.text)
        if not quiz_ids:
            return

        seen = set()
        unique_ids = []
        for qid in quiz_ids:
            if qid not in seen:
                seen.add(qid)
                unique_ids.append(qid)

        if not await _resolve_bots(client):
            await message.reply_text(
                "Cannot resolve @QuizBot or the forward bot. "
                "Make sure you have started both bots on Telegram."
            )
            return

        _trigger_chat_id = message.chat.id

        if _session is not None:
            _queue.extend(unique_ids)
            _total_in_batch += len(unique_ids)
            await message.reply_text(
                f"Added {len(unique_ids)} quiz(zes) to queue. "
                f"Total in queue: {len(_queue)}"
            )
            LOGGER.info("Queued %d quiz(zes). Queue size: %d", len(unique_ids), len(_queue))
            return

        _queue.extend(unique_ids)
        _total_in_batch = len(_queue)

        await message.reply_text(
            f"Queued {len(unique_ids)} quiz(zes). Starting…\n"
            f"Forwarding to @{_get_forward_bot()}.\n"
            f"Cooldown between quizzes: {QUIZ_DELAY_MIN // 60}–{QUIZ_DELAY_MAX // 60} minutes."
        )
        LOGGER.info("Queued %d quiz(zes). Starting first…", len(unique_ids))

        await _start_next_quiz(client)

    # ── Handler 2: File upload (.txt with quiz IDs) ───────────────────

    @app.on_message(filters.document & ~filters.user(QUIZBOT_USERNAME))
    async def handle_file_upload(client: Client, message: Message) -> None:
        global _queue, _trigger_chat_id, _total_in_batch

        doc = message.document
        if not doc or not doc.file_name:
            return
        if not doc.file_name.endswith(".txt"):
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / doc.file_name
            await message.download(file_name=str(path))
            content = path.read_text(encoding="utf-8")

        quiz_ids = QUIZ_ID_RE.findall(content)
        if not quiz_ids:
            await message.reply_text("No quiz IDs found in the file. Use format: quiz:XXXXX")
            return

        seen = set()
        unique_ids = []
        for qid in quiz_ids:
            if qid not in seen:
                seen.add(qid)
                unique_ids.append(qid)

        if not await _resolve_bots(client):
            await message.reply_text("Cannot resolve bots. Start them on Telegram first.")
            return

        _trigger_chat_id = message.chat.id

        if _session is not None:
            _queue.extend(unique_ids)
            _total_in_batch += len(unique_ids)
            await message.reply_text(
                f"Added {len(unique_ids)} quiz(zes) from file. Queue: {len(_queue)}"
            )
        else:
            _queue.extend(unique_ids)
            _total_in_batch = len(_queue)
            await message.reply_text(
                f"Loaded {len(unique_ids)} quiz(zes) from file. Starting…\n"
                f"Cooldown between quizzes: {QUIZ_DELAY_MIN // 60}–{QUIZ_DELAY_MAX // 60} minutes."
            )
            await _start_next_quiz(client)

    # ── Handler 3: /status command ────────────────────────────────────

    @app.on_message(filters.regex(r"^/status") & ~filters.user(QUIZBOT_USERNAME))
    async def handle_status(client: Client, message: Message) -> None:
        if _session:
            polls = len(_session.poll_message_ids)
            await message.reply_text(
                f"Current: quiz:{_session.quiz_id} "
                f"[{_session.queue_index}/{_session.queue_total}] "
                f"({polls} polls so far)\n"
                f"Remaining in queue: {len(_queue)}"
            )
        elif _queue:
            await message.reply_text(f"Queue has {len(_queue)} quiz(zes) but none is active.")
        else:
            await message.reply_text("No quiz in progress. Send quiz links to start.")

    # ── Handler 4: /cancel command ────────────────────────────────────

    @app.on_message(filters.regex(r"^/cancel") & ~filters.user(QUIZBOT_USERNAME))
    async def handle_cancel(client: Client, message: Message) -> None:
        global _session, _queue, _total_in_batch

        cancelled = len(_queue)
        _queue.clear()

        if _session:
            current = _session.quiz_id
            _session = None
            await message.reply_text(
                f"Cancelled quiz:{current} and {cancelled} queued quiz(zes)."
            )
        else:
            await message.reply_text(f"Cancelled {cancelled} queued quiz(zes).")

        _total_in_batch = 0
        LOGGER.info("Queue cancelled. %d quiz(zes) dropped.", cancelled)

    # ── Handler 5: Polls from QuizBot ─────────────────────────────────

    @app.on_message(filters.poll & filters.user(QUIZBOT_USERNAME))
    async def handle_quizbot_poll(client: Client, message: Message) -> None:
        if _session is None or _session.forwarding:
            return

        poll = message.poll
        if not poll or not poll.options:
            return

        _session.poll_message_ids.append(message.id)

        if _session.quizbot_chat_id == 0:
            _session.quizbot_chat_id = message.chat.id

        num_options = len(poll.options)
        option_index = random.randint(0, num_options - 1)
        selected_text = poll.options[option_index].text

        LOGGER.info(
            "[%d/%d] Poll #%d: '%s' → voting '%s'",
            _session.queue_index,
            _session.queue_total,
            len(_session.poll_message_ids),
            poll.question[:60],
            selected_text,
        )

        # Add a random delay before voting to avoid rate limits
        delay = random.uniform(VOTE_DELAY_MIN, VOTE_DELAY_MAX)
        await asyncio.sleep(delay)

        try:
            await _safe_action(
                client.vote_poll(
                    chat_id=message.chat.id,
                    message_id=message.id,
                    options=[option_index],
                ),
                label="vote_poll",
            )
        except Exception as exc:
            LOGGER.error("Failed to vote: %s", exc)

    # ── Handler 6: Non-poll messages from QuizBot ─────────────────────

    @app.on_message(~filters.poll & filters.user(QUIZBOT_USERNAME))
    async def handle_quizbot_message(client: Client, message: Message) -> None:
        if _session is None or _session.forwarding:
            return

        has_buttons = (
            message.reply_markup
            and hasattr(message.reply_markup, "inline_keyboard")
            and message.reply_markup.inline_keyboard
            and message.reply_markup.inline_keyboard[0]
        )

        if not _session.poll_message_ids:
            if has_buttons:
                button = message.reply_markup.inline_keyboard[0][0]
                LOGGER.info("QuizBot button '%s' — clicking.", button.text)
                try:
                    await message.click(0)
                except Exception as exc:
                    LOGGER.error("Failed to click '%s': %s", button.text, exc)
            _session.text_message_ids.append(message.id)
        else:
            if has_buttons:
                button_text = message.reply_markup.inline_keyboard[0][0].text
                LOGGER.info(
                    "QuizBot button '%s' after %d polls — quiz complete!",
                    button_text,
                    len(_session.poll_message_ids),
                )
                await _forward_to_bot(client, _session)
            else:
                LOGGER.info(
                    "QuizBot text after %d polls (progress?) — still waiting.",
                    len(_session.poll_message_ids),
                )

    # ── Start ─────────────────────────────────────────────────────────

    LOGGER.info(
        "Quiz Attempt Bot started — send quiz links to begin. "
        "Supports batch mode (multiple links / .txt file). "
        "Forwarding to @%s. "
        "Cooldown: %d–%d min between quizzes, %d–%ds between votes.",
        _get_forward_bot(),
        QUIZ_DELAY_MIN // 60, QUIZ_DELAY_MAX // 60,
        VOTE_DELAY_MIN, VOTE_DELAY_MAX,
    )
    app.run()


if __name__ == "__main__":
    main()
