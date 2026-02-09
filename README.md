# AME Quiz Bot Maker

A suite of Telegram bots and tools for collecting, extracting, exporting, and managing medical quiz content from Telegram. Built for the **AIAPGET Made Easy** community.

## Projects

| Project | Description | Tech |
|---------|-------------|------|
| [**bossbot**](./bossbot/) | All-in-one bot: collect forwarded quizzes, extract poll data, export to JSON/XLSX/DOCX | python-telegram-bot, openpyxl, python-docx |
| [**telegram-bot**](./telegram-bot/) | Lightweight bot to extract poll data from JSON messages between `/prepare` and `/finish` | python-telegram-bot |
| [**quiz-exporter**](./quiz-exporter/) | Bot that takes quiz JSON data and exports it to XLSX and DOCX formats | python-telegram-bot, openpyxl, python-docx |
| [**quiz-linkbot**](./quiz-linkbot/) | Bot that extracts quiz links from forwarded @QuizBot messages and sends them as a `.txt` file | python-telegram-bot |
| [**quiz-attemptbot**](./quiz-attemptbot/) | Userbot that auto-attempts quiz polls by voting a random answer (uses Pyrogram) | Pyrogram, TgCrypto |
| [**json-echo-bot**](./json-echo-bot/) | Debug bot that replies with the full JSON update payload for any message | python-telegram-bot |

### Shared Resources

| Path | Description |
|------|-------------|
| [**templates/**](./templates/) | Template files for export output (`questions_output.xlsx`, `question_output.docx`) |

## Typical Workflow

```
1. Forward quizzes from a Telegram channel/group
        │
        ▼
2. telegram-bot / bossbot collects poll data → JSON
        │
        ▼
3. quiz-exporter / bossbot exports JSON → XLSX + DOCX
```

Alternatively, use **quiz-linkbot** to batch-extract @QuizBot share links, or **json-echo-bot** to inspect raw Telegram update payloads for debugging.

## Quick Start

Each project follows the same structure:

```bash
cd <project-name>

# 1. Set up environment
cp .env.example .env
# Edit .env with your credentials

# 2. Install dependencies
make install

# 3. Run
make run
```

All projects also support Docker:

```bash
make docker-build
make docker-run
```

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather)) for bot projects
- Telegram API ID & Hash (from [my.telegram.org](https://my.telegram.org)) for the userbot (`quiz-attemptbot`)

## Project Structure

```
amequizbotmaker/
├── README.md              ← You are here
├── .gitignore             ← Central gitignore for all projects
├── bossbot/               ← All-in-one quiz bot
├── telegram-bot/          ← Poll data extractor bot
├── quiz-exporter/         ← JSON → XLSX/DOCX export bot
├── quiz-linkbot/          ← @QuizBot link extractor
├── quiz-attemptbot/       ← Auto quiz attempt userbot
├── json-echo-bot/         ← JSON debug echo bot
└── templates/             ← Shared export templates
```

## Environment Variables

Most bots require only a single environment variable:

| Variable             | Used By                  | Description                                    |
|----------------------|--------------------------|------------------------------------------------|
| `TELEGRAM_BOT_TOKEN` | All bots except attemptbot | Bot token from @BotFather                     |
| `API_ID`             | quiz-attemptbot          | Telegram API ID from my.telegram.org           |
| `API_HASH`           | quiz-attemptbot          | Telegram API hash from my.telegram.org         |
| `SESSION_STRING`     | quiz-attemptbot          | Pyrogram session string (optional, for Docker) |

## License

Private project for AIAPGET Made Easy.
