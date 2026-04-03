.PHONY: install dev test run lint clean docker-build docker-run docker-up docker-down docker-logs

install:
	uv pip install .

dev:
	uv pip install -e ".[dev]"

test:
	uv run pytest -v

run:
	uv run python -m bot.main

lint:
	uv run python -m py_compile bot/main.py
	uv run python -m py_compile bot/handlers.py
	uv run python -m py_compile bot/pipeline.py
	uv run python -m py_compile bot/parser.py
	uv run python -m py_compile bot/translator.py
	uv run python -m py_compile bot/builder.py
	uv run python -m py_compile bot/utils.py

clean:
	rm -rf __pycache__ bot/__pycache__ tests/__pycache__ .pytest_cache
	rm -rf dist build *.egg-info

docker-build:
	docker build -t bilingual-bot .

docker-run:
	docker run --rm --env-file .env bilingual-bot

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f bot
