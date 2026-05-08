FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir asyncpg structlog python-dotenv

COPY seed_system_documents.py .

# Non-root user
RUN useradd -m -u 1000 clive
USER clive

CMD ["python", "seed_system_documents.py"]
