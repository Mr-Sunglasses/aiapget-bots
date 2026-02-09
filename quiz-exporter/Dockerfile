# Build from the parent (amequizbotmaker/) directory:
#   docker build -f quiz-exporter/Dockerfile -t quizexporter .
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY quiz-exporter/pyproject.toml /app/
COPY quiz-exporter/src /app/src
COPY templates /app/templates

RUN uv sync

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "quizexporter"]
