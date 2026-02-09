.DEFAULT_GOAL := help
.PHONY: help install run lint docker-build docker-run clean

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  install       Install dependencies with uv"
	@echo "  run           Run the bot locally"
	@echo "  lint          Compile-check all Python files"
	@echo "  docker-build  Build the Docker image"
	@echo "  docker-run    Run the bot in Docker (reads .env)"
	@echo "  clean         Remove generated data and caches"

install:
	uv sync

run:
	uv run amequizbotmaker

lint:
	uv run python -m compileall src

docker-build:
	docker build -t amequizbotmaker .

docker-run:
	docker run --rm --env-file .env amequizbotmaker

clean:
	rm -rf data/ __pycache__ src/**/__pycache__ .venv
