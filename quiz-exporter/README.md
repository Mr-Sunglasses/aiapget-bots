# Quiz Exporter Bot

Telegram bot that takes quiz JSON data and exports it to XLSX and DOCX formats.

## Requirements
- Python 3.11+
- `uv`

## Setup

1. Create an environment file:

```
cp .env.example .env
```

2. Set your bot token in `.env`.

3. Install dependencies:

```
uv sync
```

## Run

```
uv run quizexporter
```

Or using make:

```
make run
```

## Usage

1. Send the bot a JSON array (as text or a `.json` file).
2. The bot returns both `questions_output.xlsx` and `question_output.docx`.

### JSON format

```json
[
  "Topic : GP 17- 26 by @AIAPGETMADEEASY",
  {
    "question": "Q- some question text",
    "options": [
      { "text": "Option A", "voter_count": 0 },
      { "text": "Option B", "voter_count": 1 }
    ],
    "correct_option_id": 1,
    "explanation": "Ans- B"
  }
]
```

- First element: title string (used as TAGS column in XLSX and title/tag in DOCX).
- Remaining elements: poll objects.

## Docker

Build from the **parent directory** (`amequizbotmaker/`):

```
docker build -f quiz-exporter/Dockerfile -t quizexporter .
docker run --rm -e TELEGRAM_BOT_TOKEN=YOUR_TOKEN quizexporter
```
