# JSON Echo Bot

A simple Telegram bot that replies with the full JSON update payload for any message you send it. Useful for inspecting the raw data Telegram sends for forwarded messages, polls, etc.

## Setup

1. Copy `.env.example` to `.env` and set your bot token:

   ```bash
   cp .env.example .env
   ```

2. Install dependencies:

   ```bash
   make install
   ```

3. Run the bot:

   ```bash
   make run
   ```

## Docker

Build and run with Docker:

```bash
make docker-build
make docker-run
```

## Usage

Send any message (text, forwarded quiz, sticker, etc.) to the bot and it will reply with the complete Telegram Update object as pretty-printed JSON.
