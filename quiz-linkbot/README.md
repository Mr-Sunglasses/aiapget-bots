# Quiz Link Bot

Telegram bot that extracts quiz links from forwarded @QuizBot messages and sends them back as a `.txt` file. Useful for batch-collecting quiz URLs from a channel or chat.

## Features

- Collect forwarded @QuizBot quiz messages
- Extract quiz IDs from inline keyboard buttons (`switch_inline_query` and `url`)
- Deduplicate quiz links automatically
- Export all collected links as a `.txt` file

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

| Command    | Description                                  |
|------------|----------------------------------------------|
| `/start`   | Show welcome message and instructions        |
| `/prepare` | Start collecting quiz messages               |
| `/finish`  | End session and receive a `.txt` file        |

### Workflow

1. Send `/prepare` to start a collection session.
2. Forward @QuizBot quiz messages to the bot.
3. Send `/finish` to get a `.txt` file with all unique quiz links.

## Docker

```bash
make docker-build
make docker-run
```

## Environment Variables

| Variable             | Required | Description                        |
|----------------------|----------|------------------------------------|
| `TELEGRAM_BOT_TOKEN` | Yes      | Telegram Bot API token             |
