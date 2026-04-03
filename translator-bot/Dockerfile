FROM python:3.11-slim AS base

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY bot/ bot/

RUN uv pip install --system --no-cache .

FROM python:3.11-slim

WORKDIR /app

COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin /usr/local/bin
COPY bot/ bot/

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "bot.main"]
