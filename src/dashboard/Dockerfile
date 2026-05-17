FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --only-binary :all: -e .

COPY clive_dashboard/ ./clive_dashboard/

RUN useradd -m -u 1000 clive
USER clive

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8084/health || exit 1

CMD ["python", "-m", "clive_dashboard.main"]
