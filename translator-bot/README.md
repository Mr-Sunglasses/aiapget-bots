# BilingualBot

A Telegram bot that converts Ayurvedic exam quiz DOCX and XLSX files into bilingual (English + Hindi) versions using the Claude API for translation.

Built for the **Sangharsh 2026** test series — handles Sanskrit, Hindi, and English Ayurvedic terminology with domain-aware translation.

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd translator-bot
uv pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in your `.env`:

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `ANTHROPIC_API_KEY` | API key from [console.anthropic.com](https://console.anthropic.com) |
| `TRANSLATION_CACHE_PATH` | Path to translation cache (default: `.translation_cache.json`) |
| `USAGE_LOG_PATH` | Path to usage log (default: `.usage_log.json`) |
| `MAX_FILE_SIZE_MB` | Max file upload size (default: `20`) |

### 3. Getting a Telegram Bot Token

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name and username for your bot
4. Copy the token BotFather gives you into `BOT_TOKEN` in `.env`

### 4. Getting an Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign up or log in
3. Navigate to **API Keys**
4. Create a new key and copy it into `ANTHROPIC_API_KEY` in `.env`

## Running

### Local

```bash
# Using uv
uv run python -m bot.main

# Or with make
make run
```

### Docker

#### Option A: Docker Compose (recommended)

The simplest way to run in production. Cache and usage logs are persisted in a Docker volume so they survive restarts.

```bash
# 1. Make sure your .env file is filled in
cp .env.example .env   # then edit with your tokens

# 2. Build and start (detached)
docker compose up -d --build

# 3. Check logs
docker compose logs -f bot

# 4. Stop
docker compose down
```

Or use the Makefile shortcuts:

```bash
make docker-up      # build + start
make docker-logs    # tail logs
make docker-down    # stop
```

#### Option B: Plain Docker

```bash
# Build the image
docker build -t bilingual-bot .

# Run (foreground)
docker run --rm --env-file .env bilingual-bot

# Run (detached)
docker run -d --name bilingual-bot --env-file .env --restart unless-stopped bilingual-bot

# View logs
docker logs -f bilingual-bot

# Stop
docker stop bilingual-bot && docker rm bilingual-bot
```

You can also pass environment variables directly instead of using `--env-file`:

```bash
docker run --rm \
  -e BOT_TOKEN=your_token \
  -e ANTHROPIC_API_KEY=your_key \
  bilingual-bot
```

## Usage

1. **Send a DOCX file** — the bot will ask for the matching XLSX
2. **Send the XLSX** (or type `/skip` to process the DOCX alone)
3. **Receive both bilingual files** back with a cost/stats summary

The bot pairs DOCX + XLSX files automatically and uses a single translation call for both, keeping them in sync.

### Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Usage instructions |
| `/skip` | Process the pending file without its pair |

## Cost Reference

- ~$0.01 per quiz (25 questions)
- 100 quizzes x $0.01 = **~$1 total**
- Repeat processing is free (cached translations)

## File Format Reference

### DOCX Parser Format

Each question block uses `#Question N`, `#Options`, `###A`–`###D`, `#Correct_option`, `#Solution`, and `#tag` markers. See `plan.md` for the full spec.

### XLSX Column Map

| Col | Header | Rule |
|-----|--------|------|
| A | S No. | Row number |
| D | TAGS | Never translate |
| F | QUESTION TEXT | Bilingual |
| G–J | OPTION1–4 | Bilingual |
| Q | RIGHT ANSWER | Integer 1–4 |
| R | EXPLANATION | Never translate |

## Development

```bash
# Install with dev dependencies
make dev

# Run tests
make test

# Lint check
make lint
```

## Project Structure

```
translator-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py          # Entrypoint, register handlers
│   ├── handlers.py      # Telegram handlers
│   ├── pipeline.py      # parse → translate → build → stats
│   ├── parser.py        # DOCX XML + XLSX → List[Question]
│   ├── translator.py    # Claude API call, cache, cost tracking
│   ├── builder.py       # Write bilingual DOCX + XLSX
│   ├── models.py        # Data classes
│   └── utils.py         # Helper functions
├── tests/
│   ├── conftest.py      # Shared fixtures + sample file generators
│   ├── test_parser.py
│   ├── test_translator.py
│   └── test_builder.py
├── .env.example
├── pyproject.toml
├── Makefile
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
└── README.md
```
