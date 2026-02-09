.DEFAULT_GOAL := help
.PHONY: help install run lint session docker-build docker-run

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  install       Install dependencies with uv"
	@echo "  run           Run the bot locally"
	@echo "  lint          Compile all python files"
	@echo "  session       Generate a Pyrogram session string (for Docker)"
	@echo "  docker-build  Build the Docker image"
	@echo "  docker-run    Run the bot in Docker"

install:
	uv sync

run:
	uv run quizattemptbot

lint:
	uv run python -m compileall src

session:
	uv run python -c "from pyrogram import Client; import os; from dotenv import load_dotenv; load_dotenv(); c = Client('quiz_attemptbot', api_id=int(os.getenv('API_ID')), api_hash=os.getenv('API_HASH')); c.start(); print('SESSION_STRING=' + c.export_session_string()); c.stop()"

docker-build:
	docker build -t quizattemptbot .

docker-run:
	docker run --rm --env-file .env quizattemptbot
