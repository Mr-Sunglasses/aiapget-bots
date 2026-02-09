FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml /app/
COPY src /app/src

RUN uv sync

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "jsonechobot"]
