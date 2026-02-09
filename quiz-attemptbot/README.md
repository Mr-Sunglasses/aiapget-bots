# Quiz Attempt Bot

A Telegram **userbot** that automatically attempts quiz polls by voting on a random answer. It uses [Pyrogram](https://docs.pyrogram.org/) to connect as your Telegram user account and listen for quiz/poll messages in any chat.

## Prerequisites

1. Go to <https://my.telegram.org> and log in with your phone number.
2. Navigate to **API development tools** and create a new application.
3. Note your **API ID** and **API Hash**.

## Setup

```bash
# Install dependencies
make install

# Copy and fill in your credentials
cp .env.example .env
# Edit .env with your API_ID and API_HASH
```

## Usage

### Run locally

```bash
make run
```

On the first run, Pyrogram will prompt you to enter your **phone number** and the **verification code** sent to your Telegram account. A session file (`quiz_attemptbot.session`) is created so you only need to authenticate once.

### Generate a session string (for Docker / headless)

```bash
make session
```

This prints a `SESSION_STRING=...` value. Copy it into your `.env` file so the bot can run without interactive login (useful for Docker).

### Docker

```bash
make docker-build
make docker-run
```

> **Note:** For Docker, you must set `SESSION_STRING` in your `.env` since interactive login is not possible inside a container.

## How it works

1. The bot connects to Telegram as **your user account** (not a bot account).
2. It listens for poll messages across all your chats.
3. When a quiz poll is received, it automatically votes on a **random option**.
4. Activity is logged to stdout.

## Environment variables

| Variable         | Required | Description                                          |
|------------------|----------|------------------------------------------------------|
| `API_ID`         | Yes      | Telegram API ID from https://my.telegram.org         |
| `API_HASH`       | Yes      | Telegram API hash from https://my.telegram.org       |
| `SESSION_STRING` | No       | Pyrogram session string for headless/Docker usage    |
