FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-build

COPY processing/ ./processing/
RUN uv sync --frozen --no-dev --no-build

RUN useradd -m -u 1000 clive
USER clive

EXPOSE 8083

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8083/health || exit 1

CMD ["python", "-m", "processing.main"]
