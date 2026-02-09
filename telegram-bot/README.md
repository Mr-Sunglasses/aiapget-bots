 # Telegram Quiz Extractor Bot
 
 This bot collects poll data from JSON messages between `/prepare` and `/finish`.
 
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
 uv run amequizbot
 ```
 
 ## Usage
 - Send `/prepare` to start collecting.
 - Send JSON messages (text) containing `message.poll`.
 - Send `/finish` to receive a JSON file with extracted data.
 
 ## Docker
 ```
 docker build -t amequizbot .
 docker run --rm -e TELEGRAM_BOT_TOKEN=YOUR_TOKEN amequizbot
 ```
