FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Copy dependency manifest first (layer caching)
COPY pyproject.toml /app/

# Copy source code
COPY src /app/src

RUN uv sync

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "amequizbotmaker"]
