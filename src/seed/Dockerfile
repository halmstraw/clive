FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-build

COPY seed_system_documents.py .

# Non-root user
RUN useradd -m -u 1000 clive
USER clive

CMD ["python", "seed_system_documents.py"]
