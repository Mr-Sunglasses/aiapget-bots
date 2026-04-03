.DEFAULT_GOAL := help
.PHONY: help install run lint docker-build docker-run

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  install       Install dependencies with uv"
	@echo "  run           Run the bot locally"
	@echo "  lint          Compile all python files"
	@echo "  docker-build  Build the Docker image"
	@echo "  docker-run    Run the bot in Docker"

install:
	uv sync

run:
	uv run cleanerbot

lint:
	uv run python -m compileall src

docker-build:
	docker build -t cleanerbot .

docker-run:
	docker run --rm --env-file .env cleanerbot
