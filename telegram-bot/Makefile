.DEFAULT_GOAL := help
.PHONY: help install run lint

help:
	echo "Usage: make <target>"
	echo ""
	echo "Targets:"
	echo "  install  Install dependencies with uv"
	echo "  run      Run the bot"
	echo "  lint     Compile all python files"

install:
	uv sync

run:
	uv run amequizbot

lint:
	uv run python -m compileall src
