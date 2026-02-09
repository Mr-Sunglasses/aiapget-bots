# Boss Bot (AME Quiz Bot Maker)

All-in-one Telegram bot that receives forwarded quizzes, extracts poll data, and exports to JSON, XLSX, and DOCX. This is the most feature-rich bot in the suite -- it combines quiz collection, JSON parsing, and multi-format export into a single bot.

## Features

- Collect forwarded Telegram quiz/poll messages
- Accept pasted JSON payloads (e.g. from the JSON Echo Bot)
- Accept uploaded `.json` files for direct export
- Auto-extract topic titles and file names from text
- Export to **JSON**, **XLSX**, and **DOCX** formats
- JSON debug echo mode (`/json` toggle)
- Persistent JSON storage in `data/` directory

## Requirements

- Python 3.11+
- `uv`

## Setup

1. Create an environment file:

   ```bash
   cp .env.example .env
   ```

2. Set your bot token in `.env`:

   ```
   TELEGRAM_BOT_TOKEN=your-telegram-bot-token
   ```

3. Install dependencies:

   ```bash
   make install
   ```

## Usage

### Run locally

```bash
make run
```

### Commands

| Command    | Description                                          |
|------------|------------------------------------------------------|
| `/start`   | Show welcome message and available commands          |
| `/prepare` | Start collecting quiz messages                       |
| `/finish`  | Export collected quizzes to JSON, XLSX & DOCX        |
| `/cancel`  | Cancel the current collection                        |
| `/json`    | Toggle JSON debug echo for the next message          |

### Workflow

1. Send `/prepare` to start a collection session.
2. Forward quiz messages (polls) to the bot, or paste JSON from the JSON Echo Bot.
3. Send `/finish` to receive JSON, XLSX, and DOCX exports.

You can also send a `.json` file directly to the bot for immediate export.

## Docker

```bash
make docker-build
make docker-run
```

## Environment Variables

| Variable             | Required | Description                        |
|----------------------|----------|------------------------------------|
| `TELEGRAM_BOT_TOKEN` | Yes      | Telegram Bot API token             |
