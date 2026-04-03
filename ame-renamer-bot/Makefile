.DEFAULT_GOAL := help
.PHONY: help install run lint docker-build docker-run docker-stop

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  install       Install dependencies with uv"
	@echo "  run           Run the bot locally"
	@echo "  lint          Compile all Python files (syntax check)"
	@echo "  docker-build  Build the Docker image"
	@echo "  docker-run    Run the bot inside Docker (requires .env)"
	@echo "  docker-stop   Stop the running Docker container"

install:
	uv sync

run:
	uv run ame-renamer-bot

lint:
	uv run python -m compileall src

docker-build:
	docker build -t ame-renamer-bot .

docker-run:
	docker run --rm --name ame-renamer-bot --env-file .env ame-renamer-bot

docker-stop:
	docker stop ame-renamer-bot || true
